"""probe_895 -- MESURE des DEUX actives de cast du boss de guilde `tauBossRiptide` :
`1194 NovaShield` et `1192 NovaBoost`.

QUESTION BINAIRE, posee AVANT la methode : **le CAST de 1194 / 1192 inflige-t-il des degats ?**
L'audit `combat-ability-coverage` les classe `DAMAGE(Particle)` -- cette colonne derive du
`damageProfile` du KIT, pas du behaviour. Le decompile dit NON : les deux `ExecuteBehaviour` ne
portent AUCUN noeud d'attaque. Patron 2-PHASES de `HeavyRailRifle` (1160).

    NovaShield$$ExecuteBehaviour :
        turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds))
        Execute( ( ( CreateShield(Caster@+0x48, Direct(GetVariableForLevel(0x27 = shieldHp)),
                                  source = AbilityOrEffect(this), turns, null, stackable=true)
                   & AddStaticStatModifierEffect(Owner@+0x30, 0x588 = 1416, statType 0x7
                                  = BLOCK_CHANCE, Direct(0x15 = blockChance), turns, isHidden=0) )
                 & AddEffect(0x587 = 1415, absRef, targets = GetMarkedTiles(), turns = NULL) )
                 & AddBondEffect(0x586 = 1414, absRef, Owner, Owner, bonded = Owner, options=ZERO) )
        GetMarkedTiles = Filter( Target@+0x60 + AdjacentTiles(Target@+0x60),
                                 NOT IsTrenchTile(ActiveTarget@+0x68) )

    NovaBoost$$ExecuteBehaviour :
        Execute( AddBondEffect(0x581 = 1409, absRef, Caster, Caster, bonded = Owner, options=ZERO)
               & AddEffect(0x582 = 1410, absRef, source = Caster, targets = GetMarkedTilesSelector(),
                           options = ZERO) )
        GetMarkedTilesSelector = Filter( AdjacentTiles(Caster@+0x48),
                                         NOT IsTrenchTile(ActiveTarget@+0x68) )

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [0] MONTAGE            : le boss EST en bataille (id remappe `GuildBoss11Boss1TauRiptide`), et
                           on RAPPORTE son empreinte (`decisionView.units[].feet`).
  [1] EXECUTION portee   : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX).
  [2] ZONE MARQUEE       : les TUILES portant 1415 / 1410, port vs natif -- ET le CONTRE-MODELE
                           « sans le filtre IsTrenchTile ». C'est l'etage DISCRIMINANT (cf. plus bas).
  [3] EMPREINTE d'effets : `{porteur -> {effectType: remaining}}` cote unite, port vs natif, LU
                           DANS LA CASCADE du cast (`Effect_RemainingTurns` au moment de la POSE) --
                           `decisionView` publie un `remaining` DEJA DECREMENTE par la fin de tour
                           que l'ability declenche.
  [4] SOURCE des effets  : la surcharge 5-args d'`AddEffect` n'a PAS de selecteur source -> chaque
                           TUILE marquee est SA PROPRE source (`Effect_SourceId == la tuile`).
                           1192 utilise la 6-args (source = Caster). Invisible du nom de la
                           fonction, lisible seulement a l'arite -- et seule la cascade l'expose.
  [5] MAGNITUDES (1194)  : `Shields_InitialAmount` natif vs le `shieldHp` du port, et
                           `BLOCK_CHANCE` apres cast. C'est l'etage qui a trouve le bug de port :
                           le natif indexe l'`AbilityState` PER-ABILITY (level 55, multiplier 200),
                           pas le canal global `ctx.active_ability_level` (0/100 sur un npc).
  [6] AUCUN DEGAT        : HP inchanges des DEUX cotes -- la refutation de l'audit.

** CE QUE LE TEMOIN DISCRIMINE, ET CE QU'IL NE DISCRIMINE PAS **
Le filtre `NOT IsTrenchTile` n'est OBSERVABLE que si la zone marquee contient une tuile `Trench`.
Le board du boss (`GB_Riptide_01`, sa carte de campagne, `battles[].BoardId`) en porte **6** ;
`MC1_67` -- le board generique -- en porte **ZERO**, donc un port SANS le filtre y serait
INDISTINGUABLE d'un port avec. Le probe CHOISIT donc ses cibles pour que le contre-modele
DIFFERE, et il l'AFFIRME (`assert marked_avec != marked_sans`) : un accord mesure sur une zone
sans trench serait une LIMITE, pas une confirmation.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_895_nova_boss_riptide.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

NOVA_BOOST = 1192              # ActiveAbilityType.NovaBoost
NOVA_CHARGE = 1193             # ActiveAbilityType.NovaCharge
NOVA_SHIELD = 1194             # ActiveAbilityType.NovaShield
NB_PENDING_ATTACK = 1409       # EffectType.NovaBoost_PendingAttack
NB_PENDING_TARGET = 1410       # EffectType.NovaBoost_PendingTarget
NS_PENDING_ATTACK = 1414       # EffectType.NovaShield_PendingAttack
NS_PENDING_TARGET = 1415       # EffectType.NovaShield_PendingTarget
NS_EXTRA_BLOCK = 1416          # EffectType.NovaShield_ExtraBlockChance

#: Le board du BOSS, pas un board generique -- et le choix est MESURE, pas esthetique :
#: `GB_Riptide_01` porte 6 tuiles `Trench`, `MC1_67` en porte 0. Sans trench dans la zone marquee,
#: le filtre `NOT IsTrenchTile` est INERTE et le temoin ne discrimine RIEN. Le board vient du
#: gameconfig (`battles/campaigns/*/battles[]` : le conteneur qui porte `boss` porte `BoardId`).
BOARD = "GB_Riptide_01"
BOSS = "tauBossRiptide:4"      # `--explicit-stats` et `--p-units` prennent la MEME chaine VERBATIM
BOSS_VISUAL = "GuildBoss11Boss1TauRiptide"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/tau.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/attack_type.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/behaviours/effects.py",
                "scripts/python/engine/entities/selectors/tiles.py",
                "scripts/python/engine/entities/triggers.py",
                "scripts/python/engine/entities/effects/magnitude.py",
                "scripts/python/rl_duel.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte les ports de 1194/1192 au NATIF via un runner live : il depend du code "
              "du port (arbre DSL + primitives CreateShield/AddEffect/AddBondEffect/"
              "AddStaticStatModifierEffect + le selecteur Trench et le trigger IsTrenchTile + la "
              "lecture de l'AbilityState per-ability), du montage (`rl_duel` resout le visualId "
              "d'un porteur npc) ET du build charge (le natif est l'oracle).",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> int:
    """`rl_duel build`. `TACTICUS_ALLOW_ROSTER_DEFICIT` n'est PAS pose : depuis #895 le garde de
    roster resout le `visualId` de config, donc un porteur npc ne rend plus un deficit fantome --
    et si le refus revient, c'est un VRAI deficit qu'on veut voir."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state_path.unlink()
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=dict(os.environ))
    if not state_path.exists() or proc.returncode != 0:
        print((proc.stderr or proc.stdout or "")[-2000:])
        raise SystemExit("build KO (rc=%s)" % proc.returncode)
    return int(json.loads(state_path.read_text())["runnerId"])


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec, bg, board


def unit_fp_live(dec) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        e = {int(x["effectType"]): x.get("remaining") for x in (u.get("effects") or [])
             if x.get("effectType") is not None}
        if e:
            out[int(u["id"])] = e
    return out


def tile_fp_live(sid, rid) -> dict:
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    out = {}
    for t in (tm.get("tiles") or []):
        e = {int(x["effectType"]): x.get("remaining") for x in (t.get("effects") or [])
             if x.get("effectType") is not None}
        if e:
            out[(int(t["col"]), int(t["row"]))] = e
    return out


def fp_off(state) -> dict:
    out = {}
    for k, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(k)] = cur
    return out


def delta(before: dict, after: dict) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[k] = new
    return out


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def cascade_effects(act: dict) -> dict:
    """`{effectType -> [ {on, source, bonded, remaining} ]}` LU DANS LA CASCADE du cast natif.

    Le SEUL canal qui publie la SOURCE et le BOND d'une instance, et le seul qui donne le
    `remaining` **A LA POSE** -- `decisionView` le rend deja decremente par la fin de tour que
    l'ability declenche. Meme lecture que `probe_491` : `kind == "group"` donne
    `instance -> NOM`, `kind == "action"` porte `tags.Effect_Id` (un id d'INSTANCE, jamais un
    `EffectType`), et la conversion se fait PAR NOM via le mirror."""
    from engine.entities.effect_type import EffectType
    nom_par_instance, out = {}, {}
    for ev in (act.get("events") or []):
        if isinstance(ev, dict) and ev.get("kind") == "group" and ev.get("source"):
            nom_par_instance[ev.get("entity")] = str(ev.get("source"))
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict) or ev.get("kind") != "action":
            continue
        raw = ev.get("tags")
        try:
            tags = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            continue
        if "Effect_SourceId" not in tags:
            continue
        nom = nom_par_instance.get(tags.get("Effect_Id"))
        etype = getattr(EffectType, nom, None) if nom else None
        if etype is None:
            continue
        out.setdefault(int(etype), []).append(
            {"on": ev.get("entity"), "source": tags.get("Effect_SourceId"),
             "bonded": tags.get("BondEffect_BondedId"),
             "remaining": tags.get("Effect_RemainingTurns")})
    return out


def cascade_shields(act: dict) -> list:
    """Les `Shields_*` de la cascade -- l'oracle natif du montant du bouclier A LA POSE."""
    out = []
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict) or ev.get("kind") != "action":
            continue
        raw = ev.get("tags")
        try:
            tags = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            continue
        if "Shields_InitialAmount" in tags:
            out.append({"on": ev.get("entity"), "amount": tags.get("Shields_InitialAmount"),
                        "turns": tags.get("Shields_TurnsLeft"),
                        "src": tags.get("Shields_ActiveAbilitySource")})
    return out


def marked_sans_filtre(board, bg, ability: int, anchor_tile: int) -> set:
    """CONTRE-MODELE : la zone marquee si le port N'AVAIT PAS le filtre `NOT IsTrenchTile`.

    1194 : `anchor + AdjacentTiles(anchor)` ; 1192 : `AdjacentTiles(caster)` seul (PAS d'origine --
    c'est l'autre difference entre les deux `GetMarkedTiles*`). `AdjacentTiles` = l'ordre NATIF
    (`neighbours_native`), origine exclue."""
    ring = set(board.neighbours_native(anchor_tile))
    return (ring | {anchor_tile}) if ability == NOVA_SHIELD else ring


def _feet_of(dec, visual_id) -> list:
    u = next((x for x in (dec.get("units") or []) if x.get("visualId") == visual_id), None)
    return list((u or {}).get("feet") or [])


def measure_shield(sid: int, seed: str = "777", state_name: str = "probe_895_shield") -> tuple:
    """1194 sur la cible `(6,2)`, dont la couronne NATIVE contient la `Trench` `(6,1)` -> le
    contre-modele « sans filtre » compte 5 tuiles contre 4 pour le modele porte.

    ⚠ La cible se choisit sur le voisinage NATIF (`Board.neighbours_native`), pas sur la geometrie
    even-q : `TileQuery$$IterateAdjacentTiles` applique une porte `|dElev| < 2` et les tuiles
    `Trench` sont a une elevation differente de leurs voisines. Premier jet de ce probe : la cible
    `(6,0)` semblait border DEUX trenches en geometrie, et son voisinage natif n'en contenait
    AUCUNE -> contre-modele identique au natif, donc un bras qui ne prouvait rien.

    Le boss est place LOIN de la cible (il ne peut pas bouger -- `moveNone` -- mais l'ability est
    TILE-TARGET whole-board)."""
    path = LOGS / ("%s.json" % state_name)
    rid = build(path, ["--seed", seed, "--board", BOARD,
                       "--explicit-stats", BOSS, "--p-units", BOSS,
                       "--a-units", "tauCrisis,orksNob",
                       "--place", "%s:3,4" % BOSS,
                       "--a-place", "tauCrisis:1,6", "--a-place", "orksNob:3,7"])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)      # MES runners, jamais ceux des autres

    try:
        return _measure(sid, rid, NOVA_SHIELD, target_pos=(6, 2)), dispose
    except Exception:
        dispose()
        raise


def measure_boost(sid: int, seed: str = "777", state_name: str = "probe_895_boost") -> tuple:
    """1192 : self-cast. Le boss est place en (6,2), dont la couronne contient la `Trench` (6,1) ;
    DEUX ennemis sont poses dessus pour armer le gate dynamique `GetDynamicInvalidCasterReason`
    (`Count(Enemies(Caster, GetMarkedTilesSelector())) > 1`), sans quoi le natif refuse le cast et
    la mesure serait vide."""
    path = LOGS / ("%s.json" % state_name)
    rid = build(path, ["--seed", seed, "--board", BOARD,
                       "--explicit-stats", BOSS, "--p-units", BOSS,
                       "--a-units", "tauCrisis,orksNob",
                       "--place", "%s:6,2" % BOSS,
                       "--a-place", "tauCrisis:5,2", "--a-place", "orksNob:5,3"])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)

    try:
        return _measure(sid, rid, NOVA_BOOST, target_pos=None), dispose
    except Exception:
        dispose()
        raise


def _measure(sid: int, rid: int, ability: int, target_pos) -> dict:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.components import ShieldComponent, StatsComponent

    state0, dec0, bg, board = load(sid, rid)
    byid = {(int(t["col"]), int(t["row"])): int(t["id"]) for t in bg["tiles"]}
    coord = {int(t["id"]): (int(t["col"]), int(t["row"])) for t in bg["tiles"]}
    terrain = {int(t["id"]): board.terrain_at(int(t["col"]), int(t["row"])) for t in bg["tiles"]}

    boss = next((u for u in (dec0.get("units") or []) if u.get("visualId") == BOSS_VISUAL), None)
    if boss is None:
        raise AssertionError("SCENARIO NON MONTE : %s absent du decisionView" % BOSS_VISUAL)
    caster_id = int(boss["id"])
    caster_tile = byid[(int(boss["pos"]["col"]), int(boss["pos"]["row"]))]
    target_id = byid[target_pos] if target_pos is not None else caster_id
    anchor = target_id if ability == NOVA_SHIELD else caster_tile

    # -- oracle natif du CIBLAGE : les cibles legales SUR PLACE (`fromHere`), jamais `targets` --
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == ability), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]

    # -- EMPREINTE du caster : le SEUL temoin natif qui la DISCRIMINE ------------------------
    # `decisionView.units[].feet` rend 1 pour TOUT LE MONDE sur ce board, donc il ne separe pas
    # « le boss occupe vraiment une tuile » de « le canal rend 1 pour tout le monde ».
    # `1193 NovaCharge` le fait, elle : son masque porte `CasterHas7Tiles` (bit 37, litteral
    # `0x2000000042` du ctor), et `TargetingQuery$$GetInvalidCasterReason` refuse quand
    # `GetFeetCount(caster) != 7`. Un boss a 1 pied doit donc rendre ZERO cible legale pour 1193,
    # la ou 1194 (aucune regle d'empreinte) en rend 66. C'est une bascule NATIVE, pas une lecture
    # de canal.
    at3 = rpc(sid, "abilityTargets",
              {"runnerId": rid, "unitId": caster_id, "abilityType": NOVA_CHARGE}, 90) or {}
    row3 = next((u for u in (at3.get("units") or []) if u.get("unitId") == caster_id), None)
    ab3 = next((a for a in ((row3 or {}).get("abilities") or [])
                if int(a.get("abilityId", -1)) == NOVA_CHARGE), {})
    charge_from_here = len(ab3.get("fromHere") or [])

    # -- OFFLINE : le MEME cast, joue par le port -------------------------------------------
    off_before, off_hp_before = fp_off(state0), hp_off(state0)
    res = _apply_active_ability(state0, caster_id, target_id, ability) or {}
    diag = res.get("diag") or {}
    off = delta(off_before, fp_off(state0))
    ent = state0.get_entity(caster_id)
    shc = ent.get_component(ShieldComponent)
    sc = ent.get_component(StatsComponent)
    off_shields = [] if shc is None else [{"amount": int(s.amount), "turns": s.remaining,
                                           "source": s.source} for s in shc.shields]
    off_block = (sc.ctx.stats.get_stat(7, 0) if sc is not None
                 and getattr(sc.ctx, "stats", None) is not None else None)
    off_hp_after = hp_off(state0)
    off_marked = {coord[k] for k, v in off.items()
                  if k in coord and (NS_PENDING_TARGET in v or NB_PENDING_TARGET in v)}
    # SOURCE cote PORT de chaque PendingTarget pose -- l'homologue exact du `Effect_SourceId` de la
    # cascade. Sans lui, l'etage [4] ne jugeait que le NATIF (il aurait donc rendu VERT sur un port
    # qui se trompe de surcharge d'`AddEffect` : mesure de contre-epreuve M3/M6).
    off_pt_sources = []
    for uid, effs in (state0.effects.by_unit or {}).items():
        for e in effs:
            if int(e.effect_type) in (NS_PENDING_TARGET, NB_PENDING_TARGET) and not e.consumed:
                off_pt_sources.append({"on": int(uid), "source": getattr(e, "source", None)})
    off_bonds = {}
    for uid, effs in (state0.effects.by_unit or {}).items():
        for e in effs:
            if int(e.effect_type) in (NS_PENDING_ATTACK, NB_PENDING_ATTACK) and not e.consumed:
                off_bonds[int(e.effect_type)] = {"on": int(uid), "bonded": getattr(e, "bonded", None),
                                                 "source": getattr(e, "source", None)}

    # -- LIVE : le MEME cast, joue par le natif ---------------------------------------------
    state_gate, _, _, _ = load(sid, rid)
    ability_obj = ABILITY_CLASSES[ability]()
    live_units_before, live_tiles_before = unit_fp_live(dec0), tile_fp_live(sid, rid)
    live_hp_before = hp_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": ability,
        "targetId": target_id}}, 120) or {}
    act0 = (act.get("actions") or [{}])[0]
    dec1 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    live_tiles = delta(live_tiles_before, tile_fp_live(sid, rid))
    live_marked = {p for p, v in live_tiles.items()
                   if NS_PENDING_TARGET in v or NB_PENDING_TARGET in v}
    casc = cascade_effects(act0)

    return {
        "rid": rid, "ability": ability, "caster": caster_id, "target": target_id,
        "caster_pos": (int(boss["pos"]["col"]), int(boss["pos"]["row"])),
        "feet": _feet_of(dec0, BOSS_VISUAL),
        "feet_all": {u.get("visualId"): len(u.get("feet") or []) for u in (dec0.get("units") or [])},
        "from_here_count": len(from_here), "target_in_from_here": target_id in from_here,
        "charge_from_here": charge_from_here,
        "ported": diag.get("ported"), "routed": res.get("routed"), "diag": diag,
        "cast_error": act0.get("error"),
        "off": off, "off_marked": off_marked, "off_bonds": off_bonds,
        "off_pt_sources": off_pt_sources,
        "off_shields": off_shields, "off_block": off_block,
        "live_units": delta(live_units_before, unit_fp_live(dec1)),
        "live_tiles": live_tiles, "live_marked": live_marked,
        "cascade": casc, "cascade_shields": cascade_shields(act0),
        "contre_modele": {coord[t] for t in marked_sans_filtre(board, bg, ability, anchor)
                          if t in coord},
        "trenches": sorted(coord[t] for t, v in terrain.items() if v == "Trench"),
        "off_hp": (off_hp_before, off_hp_after),
        "live_hp": (live_hp_before, hp_live(sid, rid)),
        "gate": {"cible": None} if target_pos is None else {},
        "ability_obj": type(ability_obj).__name__,
        "state_gate_ok": state_gate is not None,
    }


def _report(tag: str, m: dict) -> int:
    rc = 0
    ab = m["ability"]
    print("\n================ %s (ability %d) ================" % (tag, ab))
    print("[0] MONTAGE : boss u%d @%s  feet=%d %s" % (m["caster"], m["caster_pos"],
                                                      len(m["feet"]), m["feet"]))
    print("    empreintes de TOUTES les unites du board : %s" % m["feet_all"])
    print("    tuiles Trench du board : %s" % (m["trenches"],))
    print("    cibles legales SUR PLACE (fromHere) : %d ; cible retenue dans fromHere : %s"
          % (m["from_here_count"], m["target_in_from_here"]))
    # TEMOIN D'EMPREINTE : 1193 NovaCharge porte `CasterHas7Tiles` (bit 37) et refuse un caster
    # dont `GetFeetCount != 7`. Le comparer a 1192/1194 (aucune regle d'empreinte) SEPARE
    # « le canal `feet` rend 1 pour tout le monde » de « le caster occupe VRAIMENT 1 tuile ».
    feet_n = len(m["feet"])
    print("    TEMOIN D'EMPREINTE -- 1193 NovaCharge (masque `CasterHas7Tiles`) : %d cible(s) "
          "legale(s)" % m["charge_from_here"])
    if feet_n == 7 and m["charge_from_here"] == 0:
        print("    ECART : 7 pieds mais 1193 refuse -- l'un des deux canaux ment")
        rc = 1
    if feet_n != 7 and m["charge_from_here"] > 0:
        print("    ECART : %d pied(s) et 1193 ACCEPTE -- `CasterHas7Tiles` ne mord pas, donc le "
              "canal `feet` sous-compte l'empreinte reelle" % feet_n)
        rc = 1
    if feet_n != 7 and m["charge_from_here"] == 0:
        print("    COHERENT : %d pied(s) mesure(s) ET 1193 refuse -- le boss monte par ce chemin "
              "est MONO-HEX (le natif lui-meme le dit)." % feet_n)

    print("[1] EXECUTION PORTEE : routed=%s ported=%s" % (m["routed"], m["ported"]))
    if m["ported"] is not True:
        print("    ECHEC : le cast reste un NO-OP SILENCIEUX cote port")
        return 1
    if m["cast_error"]:
        print("    cast natif BLOQUE : %s" % m["cast_error"])
        return 1

    print("[2] ZONE MARQUEE (tuiles portant PendingTarget)")
    off_m, live_m, sans = m["off_marked"], m["live_marked"], m["contre_modele"]
    print("    port   : %s" % sorted(off_m))
    print("    natif  : %s" % sorted(live_m))
    print("    contre-modele SANS le filtre IsTrenchTile : %s" % sorted(sans))
    if sans == live_m:
        print("    LIMITE : le contre-modele NE DIFFERE PAS du natif -- ce bras ne prouve RIEN")
        print("             sur le filtre (aucune tuile Trench dans la zone). Ce n'est pas une")
        print("             confirmation.")
        rc = 1
    else:
        print("    DISCRIMINANT : le contre-modele differe du natif sur %s"
              % sorted(sans - live_m))
    if off_m != live_m:
        print("    ECART port/natif : port-seul=%s natif-seul=%s"
              % (sorted(off_m - live_m), sorted(live_m - off_m)))
        rc = 1

    print("[3] EMPREINTE UNITE : `remaining` A LA POSE (cascade) vs le port")
    # ⚠ ON NE COMPARE PAS `decisionView.effects[].remaining` : le cast TERMINE le tour du boss
    # (flags par defaut), donc le releve d'apres-cast est deja DECREMENTE d'un tour cote natif et
    # PAS cote port (le port ne fait pas avancer le tour). C'est un ecart de CANAL, pas de duree --
    # la cascade, elle, publie la valeur AU MOMENT de la pose.
    port_u = {k: v for k, v in m["off"].items() if k == m["caster"]}
    print("    port (unite du caster)          : %s" % port_u)
    print("    natif decisionView APRES le cast: %s   (deja decremente : fin de tour)"
          % m["live_units"])
    for et, rows in sorted(m["cascade"].items()):
        print("    cascade %d : %s" % (et, rows))
    for et, rows in sorted(m["cascade"].items()):
        on_caster = [r for r in rows if r.get("on") == m["caster"]]
        if not on_caster:
            continue
        nat = on_caster[0].get("remaining")
        nat = 0 if nat is None else int(nat)          # tag absent == duree DEFAUT (permanent)
        prt = (port_u.get(m["caster"]) or {}).get(et)
        if prt is None:
            print("    ECART : l'effet %d est ABSENT cote port" % et)
            rc = 1
        elif int(prt) != nat:
            print("    ECART de DUREE sur %d : natif(pose)=%d port=%d" % (et, nat, int(prt)))
            rc = 1

    print("[4] SOURCE des PendingTarget (la surcharge d'AddEffect, LUE DES DEUX COTES)")
    pt = NS_PENDING_TARGET if ab == NOVA_SHIELD else NB_PENDING_TARGET
    rows = m["cascade"].get(pt) or []
    prows = m["off_pt_sources"]
    nat_self = sum(1 for r in rows if r.get("on") == r.get("source"))
    prt_self = sum(1 for r in prows if r.get("on") == r.get("source"))
    print("    natif : %d instance(s), dont %d ou source == la TUILE elle-meme"
          % (len(rows), nat_self))
    print("    port  : %d instance(s), dont %d ou source == la TUILE elle-meme"
          % (len(prows), prt_self))
    if len(rows) != len(prows) or nat_self != prt_self:
        print("    ECART port/natif sur la SOURCE : la surcharge d'`AddEffect` differe "
              "(5-args = pas de selecteur source -> source == cible ; 6-args = Caster@+0x48)")
        rc = 1
    # Le SENS attendu, ability par ability -- ecrit pour que le bras ne puisse pas etre vert par
    # accord degenere (0 instance des deux cotes).
    if not rows or not prows:
        print("    LIMITE : aucune instance mesuree d'un cote -- ce bras ne prouve RIEN")
        rc = 1
    elif ab == NOVA_SHIELD and (nat_self != len(rows) or prt_self != len(prows)):
        print("    ECART : 1194 utilise la 5-args -> les %d sources doivent etre les TUILES"
              % len(rows))
        rc = 1
    elif ab == NOVA_BOOST and (nat_self != 0 or prt_self != 0):
        print("    ECART : 1192 utilise la 6-args -> AUCUNE source ne doit etre la tuile")
        rc = 1
    pa = NS_PENDING_ATTACK if ab == NOVA_SHIELD else NB_PENDING_ATTACK
    print("    bond natif %d : %s" % (pa, m["cascade"].get(pa)))
    print("    bond port  %d : %s" % (pa, m["off_bonds"].get(pa)))

    if ab == NOVA_SHIELD:
        print("[5] MAGNITUDES")
        print("    bouclier natif (cascade) : %s" % m["cascade_shields"])
        print("    bouclier port            : %s" % m["off_shields"])
        nat = [int(s["amount"]) for s in m["cascade_shields"] if s.get("amount") is not None]
        prt = [int(s["amount"]) for s in m["off_shields"]]
        if not nat or not prt or nat[0] != prt[0]:
            print("    ECART de MONTANT : natif=%s port=%s" % (nat[:1], prt[:1]))
            rc = 1
        print("    BLOCK_CHANCE port apres cast : %s" % m["off_block"])

    print("[6] AUCUN DEGAT (refutation de l'audit `DAMAGE(Particle)`)")
    ob, oa = m["off_hp"]
    lb, la = m["live_hp"]
    if ob != oa:
        print("    ECART : le PORT a change des PV -- %s -> %s" % (ob, oa))
        rc = 1
    if lb != la:
        print("    ECART : le NATIF a change des PV -- %s -> %s" % (lb, la))
        rc = 1
    if ob == oa and lb == la:
        print("    OK : HP inchanges des DEUX cotes (port %s ; natif %s)" % (ob, lb))
    return rc


def main() -> int:
    sid = _session()
    rc = 0
    print("[build] board=%s (6 tuiles Trench ; MC1_67 en porte 0 -> temoin non discriminant)"
          % BOARD)
    m, dispose = measure_shield(sid)
    try:
        rc |= _report("NovaShield 1194", m)
    finally:
        dispose()
    m2, dispose2 = measure_boost(sid)
    try:
        rc |= _report("NovaBoost 1192", m2)
    finally:
        dispose2()
    print("\nPROBE %s" % ("OK" if rc == 0 else "ECART(S)"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
