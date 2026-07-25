#!/usr/bin/env python
"""rl_duel — duel MIROIR : Claude (oracle) vs IA native, sur un runner PERSISTANT.

Le runner vit dans l'agent Frida (registry, par runnerId) entre les invocations
Python — donc on pilote le duel par sous-commandes successives :

  build              monte le runner (seed/rank/roster), sauve l'état
                     (runnerId + bc) et affiche la carte décision. Ne touche
                     JAMAIS aux runners des autres acteurs (coexistence par
                     défaut côté hooks, cap dur MAX_RUNNERS) ; remplace
                     seulement le runner de SON --state-file s'il existe.
  view               re-affiche la carte décision (mon tour).
  act move    --unit U --to C,R
  act ability --caster U --target T --ability A
  act finish  --unit U
  act endturn        fin de MON tour → passe la main à l'IA.
  aiturn             joue UN tour d'équipe de l'IA (aiPlayByUnit, capture
                     overwatch → on voit si l'IA mange l'overwatch).
  status             stage + survivants par équipe + winner.
  dispose            libère le runner.

Claude = la POLICY : à chaque tour, il lit `view`, décide, enchaîne des `act`,
puis `act endturn`, puis `aiturn`. Lancer avec `python` (psycopg3),
cf. feedback_rl_batch_python_psycopg3.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import (  # noqa: E402
    _resolve_session, _ensure_ai_trace, _load_seed_bc, _load_unspawnable,
    _normalize_and_extract_pool, _spawn_points_by_twpi,
    _patch_predefined_units, _patch_predefined_machines, _rpc,
    _load_board_dump, _load_board_pool,
    PLAYER_ID_HUMAN,
)
from rl_probe_step import _print_apply  # noqa: E402
import oracle  # noqa: E402
import stream_events  # noqa: E402
from board import Board  # noqa: E402

# La console Windows (cp1252) ne sait pas encoder les glyphes unicode de la
# carte oracle (⚠ U+26A0, box-drawing…) → force UTF-8 sur stdout/stderr pour
# que `print` ne crashe jamais selon la code page active.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "duel_state.json"


def _save_state(d: dict) -> None:
    STATE.write_text(json.dumps(d), encoding="utf-8")


def _load_state() -> dict:
    if not STATE.exists():
        print("[error] pas d'état de duel — lance `build` d'abord", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text(encoding="utf-8"))


# --- helpers partagés (dédup : routines répétées sur plusieurs commandes) ---------
def _winner_team(w) -> int | None:
    """playerId natif (3=team1 / 4=team2 ; 0/None=aucun) -> n° d'équipe ou None."""
    return {3: 1, 4: 2}.get(w)


def _winner_label(w) -> str:
    """playerId natif -> libellé lisible ('team1'/'team2'/'no-winner'/'playerN')."""
    return {0: "no-winner", 3: "team1", 4: "team2"}.get(w, f"player{w}")


def _plan_ab_map(res: dict) -> dict:
    """{(unitId, targetId): abilityId} depuis les attackPlans d'un decisionView
    (l'attaque concrète que le plan propose pour chaque cible). Auto-résolution de
    l'ability d'un cast ciblé quand le spec ne la donne pas."""
    out: dict = {}
    for p in (res.get("attackPlans") or []):
        for ev in (p.get("evals") or []):
            out[(p["unitId"], ev["targetId"])] = ev.get("abilityId")
    return out


def _decision(sid: int, rid: int, maxrank: int = 8) -> dict:
    # allAbilities=True : expose AUSSI les actifs de chaque unité (id + dégâts
    # rankés), pas seulement l'attaque normale. Sans ça, decisionView ne liste
    # que NormalAttackType → mes actifs (SanctorumMissile, VexillaMagnifica, …)
    # restent invisibles dans les plans (cf. asymétrie apparente moi/adversaire :
    # il n'y en a pas, c'est juste ce flag qui défaut à false côté hook).
    return (_rpc(sid, "decisionView",
                 [{"runnerId": rid, "maxRank": maxrank, "allAbilities": True}],
                 timeout=300).get("result") or {})


def _turn_no(st: dict) -> int:
    """Mon n° de tour FIABLE (monotone) = nb d'endturn déjà joués + 1, dérivé de
    l'action_log du state-file (même logique que le guard). Remplace dans l'en-tête
    `view` le compteur per-player oscillant `view.turn` (TF14)."""
    return sum(1 for x in (st.get("action_log") or []) if x.get("kind") == "endturn") + 1


def _show_card(sid: int, rid: int, bc: dict, pov_team: int | None = None,
               turn_no: int | None = None) -> dict:
    res = _decision(sid, rid)
    if not res.get("ok"):
        print(f"[view] decisionView ERROR: {res.get('error')}")
        return res
    # abilityTargets : enrichit MES ACTIFS avec la légalité now/+move des actifs
    # (incl. NON-attaque buff/heal/summon/hex, absentes des attackPlans). Best-effort.
    abil = (_rpc(sid, "abilityTargets",
                 [{"runnerId": rid, "allAbilities": True}], timeout=120)
            .get("result") or {})
    print(oracle.build_card(res, Board(bc), abil=abil if abil.get("ok") else None,
                            round_cap=_env_bombardment_cap(bc),
                            pov_team=pov_team, turn_no=turn_no))
    return res


def _env_bombardment_cap(bc: dict):
    """nrOfRounds de l'EnvEndBombardment SI ce combat a l'env ability active, sinon
    None. RE (ghidra) : le Warning/Incoming s'arme quand le compteur de round atteint
    `nrOfRounds` (=8 sur nos configs) ; le nuke board-wide (healthPct% des PV max,
    =20%) fire ~1 round après. Lecture depuis le `bc` du state-file : EnvironmentAbilities
    (l'env l'a-t-il ?) + Constants.nrOfRounds (la config de l'ability)."""
    if not isinstance(bc, dict):
        return None
    has_env = [False]
    cap = [None]

    def walk(o):
        if isinstance(o, dict):
            ea = o.get("EnvironmentAbilities")
            if isinstance(ea, list):
                for it in ea:
                    if isinstance(it, dict) and it.get("ConfigId") == "EnvEndBombardment":
                        has_env[0] = True
            eb = o.get("EnvEndBombardment")
            if isinstance(eb, dict):
                c = (eb.get("Constants") or {}).get("nrOfRounds")
                if c is not None:
                    try:
                        cap[0] = int(c)
                    except (TypeError, ValueError):
                        pass
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(bc)
    return cap[0] if has_env[0] else None


def _advance(sid: int, rid: int, n: int, maxpump: int) -> None:
    played = 0
    while played < n:
        chunk = min(2, n - played)
        r = (_rpc(sid, "aiPlayByUnit",
                  [{"runnerId": rid, "maxTurns": chunk, "maxActivations": 9999,
                    "maxPump": maxpump}], timeout=180).get("result") or {})
        if not r.get("ok"):
            print(f"  [advance] ERROR: {r.get('error')}"); break
        played += r.get("turnsPlayed") or 0
        if r.get("finalStage") != 1:
            break


def _plans_summary(res: dict) -> None:
    """Ré-évaluation compacte APRÈS une action : HP ennemis vivants + plans
    d'attaque restants de mes units (base de décision pour l'action suivante)."""
    units = res.get("units") or []
    enemies = [u for u in units if not u.get("ctrl") and u.get("alive")]
    print("  -- ennemis vivants : "
          + ", ".join(f"u{e['id']}[{e.get('visualId')}] hp={e.get('hp')}"
                      for e in enemies))
    toact = res.get("toActivate") or []
    print(f"  -- mes units à activer : {toact}")
    for p in (res.get("attackPlans") or []):
        if p.get("unitId") not in toact:
            continue
        best = []
        for ev in (p.get("evals") or []):
            r0 = (ev.get("ranked") or [None])[0]
            if not r0 or r0.get("dmgMax") is None:
                continue
            km = ("K!" if r0.get("killSure") else "K?" if r0.get("kill") else "")
            best.append(f"u{ev['targetId']}@({r0['col']},{r0['row']})"
                        f"[{r0['dmgMin']}-{r0['dmgMax']}{km}]")
        if best:
            print(f"     u{p['unitId']}: " + "  ".join(best))


def _alive_by_team(units: list) -> dict:
    out: dict = {}
    for u in units:
        if u.get("alive"):
            out[u.get("team")] = out.get(u.get("team"), 0) + 1
    return out


def _parse_ids(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _board_mow_ok(bc: dict) -> bool:
    """True si la board de la BC a un slot MoW (MachineOfWarPosition) pour les
    deux camps sur le SpawnPointSet actif — sinon le MoW drop silencieusement
    au déploiement (cf. _board_supports_mow / project_mow_deploy_gate)."""
    spsets = (bc.get("Board") or {}).get("SpawnPointSets") or []
    idx = bc.get("SpawnPointSetIndex") or 0
    if not (0 <= idx < len(spsets)):
        return False
    mp = {g.get("TeamWithPlayerIndex"): g.get("MachineOfWarPosition")
          for g in (spsets[idx].get("SpawnPointGroups") or [])}
    return mp.get(0) not in (0, None) and mp.get(1) not in (0, None)


def cmd_build(sid: int, a) -> int:
    # Board swap (--board id fixe / --board-pool aleatoire) — mirror rl_collect_batch.
    if getattr(a, "board", None) and getattr(a, "board_pool", None):
        print("[error] --board et --board-pool sont mutuellement exclusifs", file=sys.stderr)
        return 2
    # Board OBLIGATOIRE (sauf --list-pool) : le seed BC est un skeleton dont le board
    # par defaut (capture live) n'a pas de spawns 5v5 fiables -> il FAUT choisir un board
    # dumpe (cf. #159). `python dump_boards.py` regenere data/boards/ ; ids via board.py.
    if not a.list_pool and not getattr(a, "board", None) and not getattr(a, "board_pool", None):
        print("[error] choisis un board : --board <id> (ex. MC1_67, C4_09) ou "
              "--board-pool <pvp|syncPvp|global>. Voir data/boards/ (dump_boards.py) "
              "et board.py pour les ids/terrains.", file=sys.stderr)
        return 2
    fixed_board_dump = None
    if getattr(a, "board", None):
        try:
            fixed_board_dump = _load_board_dump(a.board)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
        _bi = fixed_board_dump.get("board") or {}
        print(f"[build] board swap (fixe): id={fixed_board_dump.get('id')} "
              f"kind={fixed_board_dump.get('kind')} {_bi.get('Width')}x{_bi.get('Height')} "
              f"sps={fixed_board_dump.get('spawnPointsSet')}")
    seed_bc = _load_seed_bc(getattr(a, "seed_bc", None))
    # --board fixe : swap au moment de la normalisation (buildNormalizedBC boardJson+spawnPointSetIndex).
    template_bc, pool, pool_mow = _normalize_and_extract_pool(
        sid, seed_bc, a.rank, board_dump=fixed_board_dump)
    bad_u, bad_mow = _load_unspawnable(a.rank)
    pool = [u for u in pool if u not in bad_u]
    pool_mow = [u for u in pool_mow if u not in bad_mow]

    if a.list_pool:
        print(f"[pool] rank {a.rank} — {len(pool)} units régulières spawnables :")
        for uid in pool:
            print("  ", uid)
        print(f"[pool] {len(pool_mow)} MoW spawnables : {pool_mow}")
        return 0

    rng = random.Random(a.seed)
    explicit_p = _parse_ids(a.p_units)
    explicit_a = _parse_ids(a.a_units)

    def pick(label: str, explicit: list[str] | None, n: int) -> list[str]:
        if explicit:
            miss = [u for u in explicit if u not in pool]
            if miss:
                print(f"[error] {label}: hors pool / non spawnables au rank "
                      f"{a.rank}: {miss}", file=sys.stderr)
                print(f"        pool = {len(pool)} units (voir `build --list-pool`)",
                      file=sys.stderr)
                sys.exit(2)
            return list(explicit)
        return rng.sample(pool, n)

    p_units = pick("--p-units", explicit_p, a.roster)
    a_units = pick("--a-units", explicit_a, a.roster)

    # MoW : explicite, ou auto (--mow), ou aucun.
    p_mow, a_mow = a.p_mow, a.a_mow
    if a.mow and not p_mow and not a_mow and pool_mow:
        p_mow, a_mow = rng.choice(pool_mow), rng.choice(pool_mow)
    for label, m in (("--p-mow", p_mow), ("--a-mow", a_mow)):
        if m and m not in pool_mow:
            print(f"[error] {label}={m} hors pool MoW spawnable: {pool_mow}",
                  file=sys.stderr)
            return 2

    bc = copy.deepcopy(template_bc)
    # --board-pool : board aleatoire (post-normalisation, car le filtre MoW a besoin de pool_mow).
    # Swap direct sur la BC (Board + SpawnPointSetIndex apparie) ; les spawns joueur sont re-derives
    # plus bas depuis le nouveau board.
    if getattr(a, "board_pool", None):
        require_mow = bool(p_mow or a_mow)
        try:
            _bpool = _load_board_pool(a.board_pool, a.roster, require_mow)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
        if not _bpool:
            print(f"[error] pool de boards vide pour kind={a.board_pool!r}"
                  f"{' (contrainte MoW)' if require_mow else ''}", file=sys.stderr)
            return 2
        _pick = random.Random(a.seed).choice(_bpool)
        bc["Board"] = _pick["board"]
        bc["SpawnPointSetIndex"] = _pick["spawnPointsSet"]
        _pi = _pick.get("board") or {}
        print(f"[build] board swap (pool {a.board_pool}): id={_pick.get('id')} "
              f"{_pi.get('Width')}x{_pi.get('Height')} sps={_pick.get('spawnPointsSet')} "
              f"({len(_bpool)} eligibles)")
    _patch_predefined_units(bc, a_units)
    _patch_predefined_machines(bc, p_mow, a_mow)

    # --crit/--block "CC,CD" : restaure des stats de combat sur les TEMPLATES Units des
    # p-units (la normalisation les remet à 0 ; AddUnit honore le template, cf. probe). Sert
    # à tester crit/block en combat — le crit d'un héros vient des items I_Crit (cf. itemSlots),
    # absent d'un build frais. --crit-target applique aussi à l'adversaire.
    def _patch_combat_stat(visual_ids: set[str], field_c: str, field_d: str, spec: str):
        cc, cd = (int(x) for x in spec.split(","))
        for u in bc.get("Units", []):
            if u.get("VisualId") in visual_ids:
                u[field_c] = cc; u[field_d] = cd
    p_set, a_set = set(p_units), set(a_units)
    if getattr(a, "crit", None):
        _patch_combat_stat(p_set, "CritChance", "CritDamage", a.crit)
    if getattr(a, "crit_target", None):
        _patch_combat_stat(a_set, "CritChance", "CritDamage", a.crit_target)
    if getattr(a, "block_target", None):
        _patch_combat_stat(a_set, "BlockChance", "BlockDamage", a.block_target)
    if getattr(a, "hp_target", None):
        # Cible « one-shottable » : PV bas (Health + RemainingHealth) ET armure nulle (Armor/FixedArmor=0)
        # sur les a-units → un allié one-shot pour un kill DÉTERMINISTE (validation du vecteur MORT
        # ActOfFaith). AddUnit honore le template (cf. --crit). N'affecte que les builds de test qui
        # passent --hp-target.
        for u in bc.get("Units", []):
            if u.get("VisualId") in a_set:
                u["Health"] = a.hp_target
                u["RemainingHealth"] = a.hp_target
                u["Armor"] = 0
                u["FixedArmor"] = 0
    if getattr(a, "hp_player", None):
        # Idem --hp-target mais côté JOUEUR : mover fragile (p-unit) pour un kill déterministe quand
        # l'overwatcher est une a-unit (l'effet Overwatch 1009 se pose côté IA au déploiement).
        for u in bc.get("Units", []):
            if u.get("VisualId") in p_set:
                u["Health"] = a.hp_player
                u["RemainingHealth"] = a.hp_player
                u["Armor"] = 0
                u["FixedArmor"] = 0
    if getattr(a, "dmg_target", None):
        # Frappe ADVERSE écrasante : `Damage` des a-units (la normalisation rend un chiffre bas —
        # ~30 dmg/coup mesuré, insuffisant pour tuer une unité INVOQUÉE dont les PV viennent du kit
        # du summoner et non du roster, donc hors de portée de --hp-target/--hp-player). Sert à
        # DÉTRUIRE des summons à la demande (case-38 : exercer `alive < cap <= everSpawned`, la
        # branche « morts inclus » de `IdunBattle.Entities.UnitExtensions$$GetChildrenCount`).
        for u in bc.get("Units", []):
            if u.get("VisualId") in a_set:
                u["Damage"] = a.dmg_target

    if (p_mow or a_mow) and not _board_mow_ok(bc):
        print("[warn] board de la seed BC SANS slot MoW (MachineOfWarPosition) "
              "→ le MoW sera DROP silencieusement au déploiement. Il faut une "
              "board MoW-capable (cf. _board_supports_mow).", file=sys.stderr)

    spawns = _spawn_points_by_twpi(bc)
    player_pts = spawns.get(0) or []
    roster_p = len(p_units)
    if len(player_pts) < roster_p:
        print(f"[error] {len(player_pts)} spawns joueur < {roster_p} units",
              file=sys.stderr)
        return 2
    player_units = [
        {"unitId": p_units[i], "playerId": PLAYER_ID_HUMAN,
         "col": int(player_pts[i][0]), "row": int(player_pts[i][1])}
        for i in range(roster_p)
    ]
    # Replace SCOPE par acteur : cote hooks la coexistence est le DEFAUT
    # (initAndStart ne dispose plus jamais les runners freres ; cap dur
    # MAX_RUNNERS=10 sinon refus explicite). Rebuild = remplacer LE runner
    # enregistre dans CE --state-file (celui que _save_state va ecraser),
    # pas les freres — sinon il deviendrait orphelin et mangerait le cap.
    if STATE.exists():
        try:
            old_rid = json.loads(STATE.read_text(encoding="utf-8")).get("runnerId")
        except Exception:
            old_rid = None
        if old_rid is not None:
            _rpc(sid, "disposeRunner", [{"runnerId": old_rid}], timeout=15)
            print(f"[build] ancien runner {old_rid} du state-file dispose")
    init_resp = _rpc(sid, "initAndStart",
                     [{"configJson": json.dumps(bc), "seed": a.seed,
                       "playerUnits": player_units}], timeout=40)
    init = init_resp.get("result") or {}
    rid = init.get("runnerId")
    if rid is None:
        # Surface the real RPC error (was masked by `or {}` — the host
        # returns it in `error`, not `result`, when initAndStart throws).
        print(f"[error] initAndStart: {init_resp.get('error') or init_resp}",
              file=sys.stderr)
        return 2
    mow_str = (f"  MoW: moi={p_mow or '-'} IA={a_mow or '-'}"
               if (p_mow or a_mow) else "")
    print(f"[build] runnerId={rid}  MON roster (team 1)={p_units}")
    print(f"[build] roster ADVERSE (team 2)={a_units}{mow_str}")
    if a.advance > 0:
        _advance(sid, rid, a.advance, a.maxpump)
        print(f"[build] advanced {a.advance} tours (IA vs IA)")
    res = _show_card(sid, rid, bc)
    my_team = next((u.get("team") for u in (res.get("units") or [])
                    if u.get("ctrl")), None)
    _save_state({"runnerId": rid, "bc": bc, "seed": a.seed, "myTeam": my_team,
                 "playerUnits": player_units})
    return 0


def cmd_view(sid: int, a) -> int:
    st = _load_state()
    _show_card(sid, st["runnerId"], st["bc"],
               pov_team=st.get("myTeam"), turn_no=_turn_no(st))
    return 0


def _moves_grid(uid: int, vis, uc: int, ur: int, reach: set, occ: dict) -> str:
    """Grille ASCII CROPPÉE des tuiles légales d'UNE unité (cf. cmd_moves).
    @ =unité · o =move légal · M/e =autre unité (bloque) · . =inatteignable."""
    cells = reach | {(uc, ur)}
    cols = [c for c, _ in cells]
    rows = [r for _, r in cells]
    c0, c1 = max(0, min(cols) - 1), max(cols) + 1
    r0, r1 = max(0, min(rows) - 1), max(rows) + 1
    out = [f"=== MOVES u{uid} [{vis}] @({uc},{ur}) -> {len(reach)} tuiles légales ===",
           "    " + " ".join(f"{c}" for c in range(c0, c1 + 1))]
    for r in range(r0, r1 + 1):
        cs = []
        for c in range(c0, c1 + 1):
            if (c, r) == (uc, ur):
                cs.append("@")
            elif (c, r) in occ:
                cs.append(occ[(c, r)])
            elif (c, r) in reach:
                cs.append("o")
            else:
                cs.append(".")
        out.append(f"r{r:>2} " + " ".join(cs))
    return "\n".join(out)


def cmd_moves(sid: int, a) -> int:
    """Grilles ASCII des MOVES LÉGAUX par unité du joueur courant (via aiMovableTiles).
    Comble le trou d'info qui faisait deviner des moves ILLÉGAUX (H55) : la carte `view`
    ne donne que la range + les plans d'ATTAQUE, PAS le set de repositionnement résolu
    (creusé par blockers/terrain/BFS réel). À lancer AVANT un repositionnement (move sans
    attaque). `--unit U` = une seule unité."""
    st = _load_state()
    rid = st["runnerId"]
    mov = (_rpc(sid, "aiMovableTiles", [{"runnerId": rid}], timeout=60).get("result") or {})
    if not mov.get("units"):
        print(f"[moves] aiMovableTiles vide/erreur : {mov.get('error') or mov}")
        return 2
    dec = _decision(sid, rid)
    occ: dict = {}  # (col,row) -> 'M' (moi) | 'e' (ennemi) : autres unités vivantes (bloquent)
    vis_by_id: dict = {}
    for u in (dec.get("units") or []):
        vis_by_id[u.get("id")] = u.get("visualId")
        p = u.get("pos") or {}
        c, r = p.get("col"), p.get("row")
        if c is not None and u.get("alive"):
            occ[(c, r)] = "M" if u.get("ctrl") else "e"
    want = a.unit
    n = 0
    for mu in mov.get("units"):
        uid = mu.get("unitId")
        if want is not None and uid != want:
            continue
        up = mu.get("pos") or {}
        uc, ur = up.get("col"), up.get("row")
        if uc is None:
            continue
        reach = {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                 if t.get("col") is not None and t.get("row") is not None}
        print(_moves_grid(uid, vis_by_id.get(uid, "?"), uc, ur, reach, occ))
        n += 1
    if n == 0:
        print("[moves] rien à afficher"
              + (f" (u{want} hors movable set : déjà agi / non contrôlée / morte ?)"
                 if want is not None else ""))
        return 2
    print("  [moves] @ =unité · o =move légal · M/e =autre unité (bloque) · "
          ". =inatteignable")
    return 0


def _tgt_fmt(t: dict) -> str:
    if t.get("kind") == "unit":
        tp = t.get("pos") or {}
        return (f"u{t.get('targetId')}[{t.get('visualId')}]"
                f"@({tp.get('col')},{tp.get('row')})")
    ti = t.get("tile") or {}
    return f"tile({ti.get('col')},{ti.get('row')})"


def _tgt_key(t: dict):
    if t.get("kind") == "unit":
        return ("u", t.get("targetId"))
    ti = t.get("tile") or {}
    return ("t", ti.get("col"), ti.get("row"))


def cmd_abilities(sid: int, a) -> int:
    """Cibles LÉGALES par (unité, ability) du joueur courant — l'analogue ability de
    `moves`, pour TOUTES les abilities (y compris NON-attaque : buff/heal/summon/hex,
    absentes des plans d'attaque de `view`). Via le RPC `abilityTargets` (= la query
    que l'IA `BasePlaybook` consomme). DEUX listes par ability :
      now    = castable SANS bouger (fromHere ; légalité EXACTE du cast immédiat) ;
      +move  = atteignable CE TOUR en bougeant d'abord (superset \\ now).
    ∉ des deux => cast DÉFINITIVEMENT no-op. `--unit U` / `--ability A` pour filtrer."""
    st = _load_state()
    rid = st["runnerId"]
    body: dict = {"runnerId": rid, "allAbilities": True}
    if a.unit is not None:
        body["unitId"] = a.unit
    if a.ability is not None:
        body["abilityType"] = a.ability
    res = (_rpc(sid, "abilityTargets", [body], timeout=120).get("result") or {})
    if not res.get("ok"):
        print(f"[abilities] abilityTargets ERROR: {res.get('error')}")
        return 2
    units = res.get("units") or []
    if not units:
        print("[abilities] aucune unité contrôlée vivante à scanner")
        return 2
    fh_ok = res.get("fromHereResolved")
    print(f"=== ABILITY TARGETS (joueur {res.get('playerId')} · {res.get('ms')}ms · "
          f"mutated={res.get('mutated')} · fromHere={'OK' if fh_ok else 'INDISPO'}) ===")
    for u in units:
        pos = u.get("pos") or {}
        print(f"\nu{u.get('unitId')} [{u.get('visualId')}] "
              f"@({pos.get('col')},{pos.get('row')})")
        for ab in (u.get("abilities") or []):
            flags = []
            if ab.get("usable") is not None:
                flags.append("usable" if ab.get("usable") else "NOT-usable")
            if ab.get("cooldown"):
                flags.append(f"cd={ab.get('cooldown')}")
            if ab.get("disabled"):
                flags.append("disabled")
            fl = (" {" + ",".join(flags) + "}") if flags else ""
            tgts = ab.get("targets") or []
            here = ab.get("fromHere") or []
            here_keys = {_tgt_key(t) for t in here}
            move_only = [t for t in tgts if _tgt_key(t) not in here_keys]
            if ab.get("err"):
                desc = f"ERR {ab.get('err')}"
            elif not fh_ok:
                # pas de fromHere → on ne montre que le superset (sémantique d'avant).
                desc = (f"{len(tgts)} (move inclus) → " + ", ".join(_tgt_fmt(t) for t in tgts)
                        if tgts else "AUCUNE cible ce tour")
            elif not tgts:
                desc = "AUCUNE cible (no-op certain)"
            else:
                seg = []
                if here:
                    seg.append(f"now[{len(here)}]: " + ", ".join(_tgt_fmt(t) for t in here))
                else:
                    seg.append("now: ∅")
                if move_only:
                    seg.append(f"+move[{len(move_only)}]: "
                               + ", ".join(_tgt_fmt(t) for t in move_only))
                desc = " · ".join(seg)
            print(f"  [{ab.get('kind')}] {ab.get('ability')} "
                  f"(id{ab.get('abilityId')}){fl}: {desc}")
    print("\n  [abilities] now = castable SANS bouger (légalité exacte du cast immédiat) · "
          "+move = atteignable ce tour en bougeant d'abord · ∉ des deux => no-op certain.")
    return 0


def cmd_reason(sid: int, a) -> int:
    """Raison STRUCTURÉE d'un cast invalide (refinement 2) — RPC `abilityReason` →
    flag `TargetingRule` décodé en noms. `--caster U --ability A [--target T]`. Sans
    --target : seulement la raison CASTER (peut-elle caster du tout)."""
    st = _load_state()
    rid = st["runnerId"]
    if a.caster is None or a.ability is None:
        print("[reason] requiert --caster U --ability A [--target T]")
        return 2
    body: dict = {"runnerId": rid, "casterId": a.caster, "abilityType": a.ability}
    if a.target is not None:
        body["targetId"] = a.target
    r = (_rpc(sid, "abilityReason", [body], timeout=60).get("result") or {})
    if not r.get("ok"):
        print(f"[reason] ERROR: {r.get('error')}")
        return 2
    print(f"=== ABILITY REASON caster u{r.get('casterId')} · ability "
          f"{r.get('abilityType')} · target {r.get('targetId')} ===")
    # TF24 : état LIVE (cooldown/usable/disabled) — la couche targeting ci-dessous
    # ne connaît PAS le cooldown (rend ValidRequest même cooldown-locked).
    ast = r.get("abilityState")
    if ast is not None:
        cd = ast.get("cooldown")
        flags = []
        if cd:
            flags.append(f"cooldown={cd}")
        if ast.get("disabled"):
            flags.append("disabled")
        if ast.get("usable") is False:
            flags.append("usable=false")
        if not flags:
            flags.append("prêt")
        warn = "  ⚠ targeting peut dire VALID mais COOLDOWN actif" if cd else ""
        print(f"  ÉTAT LIVE: {', '.join(flags)}{warn}")
    else:
        print("  ÉTAT LIVE: (indisponible — attaque normale ou ability-machine "
              "Primary/Secondary sans objet ActiveAbility)")
    for key, lab in (("casterReason", "CASTER"), ("targetReason", "CIBLE")):
        rr = r.get(key)
        if rr is None:
            print(f"  {lab}: (non évalué)")
            continue
        rc = rr.get("ruleClass")
        if rr.get("reasons"):
            print(f"  {lab}: {','.join(rr['reasons'])}  [{rr.get('hex')}]")
        elif rc and rc != "NoBrokenTargetingRule":
            print(f"  {lab}: {rc} (règle non décodable en flag)")
        else:
            print(f"  {lab}: aucune règle cassée (cible VALIDE)")
    return 0


def cmd_act(sid: int, a) -> int:
    st = _load_state()
    rid = st["runnerId"]
    res = _decision(sid, rid)
    my_ids = [u["id"] for u in (res.get("units") or []) if u.get("ctrl")]
    if a.kind == "move":
        col, row = (int(x) for x in a.to.split(","))
        action = {"kind": "move", "unitId": a.unit, "to": {"col": col, "row": row}}
        label = f"MOVE u{a.unit}->({col},{row})"
    elif a.kind == "ability":
        ability = a.ability
        if ability is None:  # auto-résout depuis le plan (caster→target)
            for p in (res.get("attackPlans") or []):
                if p.get("unitId") == a.caster:
                    for ev in (p.get("evals") or []):
                        if ev.get("targetId") == a.target:
                            ability = ev.get("abilityId")
        if ability is None:
            print(f"[act] pas de plan {a.caster}->{a.target} (hors portée ?), "
                  f"passe --ability (obligatoire pour --to / les actifs)"); return 2
        # Cible : entité (--target) OU hex LIBRE (--to col,row → entité-tuile côté
        # hook). --to sert aux abilities sur-hex : summons (AlphaWarrior,
        # ForwardSpotter), mur (DutyEternal), marquage sur case vide. --ability
        # est alors OBLIGATOIRE (pas de plan auto-résolu sans cible ennemie).
        if a.target is not None:
            action = {"kind": "ability", "casterId": a.caster,
                      "targetId": a.target, "abilityType": ability}
            label = f"ABILITY {ability} u{a.caster}->u{a.target}"
        elif a.to is not None:
            col, row = (int(x) for x in a.to.split(","))
            action = {"kind": "ability", "casterId": a.caster,
                      "to": {"col": col, "row": row}, "abilityType": ability}
            label = f"ABILITY {ability} u{a.caster}->hex({col},{row})"
        else:
            print("[act] ability: passe --target <id> (entité) ou --to col,row (hex)")
            return 2
    elif a.kind == "finish":
        action = {"kind": "finish", "unitId": a.unit}
        label = f"FINISH u{a.unit}"
    elif a.kind == "endturn":
        action = {"kind": "endturn"}
        label = "ENDTURN"
    else:
        print(f"[act] kind inconnu: {a.kind}"); return 2
    r = (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
              timeout=60).get("result") or {})
    _print_apply(label, r, my_ids)
    print(f"  -> stage={r.get('stage')} currentPlayer={r.get('currentPlayer')}")
    # CAPTURE dataset IL — SYMÉTRIE avec cmd_play (l.853/884) : `act` DOIT logger comme
    # `play`, sinon une trajectoire jouée 100% en `act` = action_log VIDE → démo perdue
    # (ex. seed 80031 b6 : un VAINQUEUR joué entièrement via `act`, team2 archivé 0 action).
    # On logge l'action RÉUSSIE (même critère d'échec que cmd_play) + save par-action.
    if a.kind == "endturn":
        st.setdefault("action_log", []).append({"kind": "endturn"})
        _save_state(st)
    else:
        fail = _action_failed(r, a.kind, sid, rid, action)
        if fail:
            print(f"  [act] /!\\ action ÉCHOUÉE -> NON loggée (rien donné à l'IA) : {fail}")
        else:
            st.setdefault("action_log", []).append(action)
            _save_state(st)
    # Ré-évaluation APRÈS l'action (le board a changé) — base de la décision
    # suivante, surtout pour le focus-fire (arrêter dès qu'une cible meurt).
    if a.kind != "endturn":
        _plans_summary(_decision(sid, rid))
    return 0


def _my_team(sid: int, rid: int, st: dict):
    t = st.get("myTeam")
    if t is not None:
        return t
    res = _decision(sid, rid)
    return next((u.get("team") for u in (res.get("units") or [])
                 if u.get("ctrl")), None)


def _fmt_dmg(d: dict) -> str:
    eff = f" [{d['effect']}]" if d.get("effect") else ""
    auto = f" [AUTO:{d.get('group')}]" if d.get("auto") else ""
    crit = "*" if d.get("crit") else ""
    kill = " KILL" if d.get("killed") else ""
    return (f"u{d.get('attacker')}->u{d.get('target')} "
            f"{d.get('amount')}{crit}{eff}{auto}{kill}")


def _summarize_cascade(an: dict, cap: int = 16) -> None:
    """Bilan UNIFORME de la cascade (overwatch/counter/aura/DoT = events comme
    les autres, juste labellisés via `effect`). received = ce que J'ENCAISSE ;
    dealt (pendant le tour adverse) = MA réaction (overwatch/contre/aura)."""
    rec, dealt = an.get("received") or [], an.get("dealt") or []
    if rec:
        tot = sum(d.get("amount") or 0 for d in rec)
        nk = sum(1 for d in rec if d.get("killed"))
        na = sum(1 for d in rec if d.get("auto"))
        print(f"  SUBI : {len(rec)} coups, {tot} dmg"
              + (f", {nk} de MES units tuées" if nk else "")
              + (f", dont {na} AUTO/passif (TheBetrayer/triggered/riposte)"
                 if na else ""))
        for d in rec[:cap]:
            print("    - " + _fmt_dmg(d))
        if len(rec) > cap:
            print(f"    … (+{len(rec) - cap})")
    if dealt:
        tot = sum(d.get("amount") or 0 for d in dealt)
        nk = sum(1 for d in dealt if d.get("killed"))
        print(f"  MA RÉACTION (overwatch/contre/aura) : {len(dealt)} coups, "
              f"{tot} dmg" + (f", {nk} ennemis tués en réaction" if nk else ""))
        for d in dealt[:cap]:
            print("    - " + _fmt_dmg(d))
        if len(dealt) > cap:
            print(f"    … (+{len(dealt) - cap})")
    if not rec and not dealt:
        print("  (aucun dégât dans la cascade)")


def _ai_turn(sid: int, rid: int, maxpump: int, my_team) -> dict:
    r = (_rpc(sid, "aiPlayByUnit",
              [{"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                "maxPump": maxpump, "captureEvents": True}],
              timeout=300).get("result") or {})
    print(f"[aiturn] ok={r.get('ok')} turnsPlayed={r.get('turnsPlayed')} "
          f"stop={r.get('stopReason')} finalStage={r.get('finalStageName')} "
          f"finalPlayer={r.get('finalPlayer')} events={r.get('cascadeCount')}")
    res = _decision(sid, rid)
    units = res.get("units") or []
    # my_ids inclut mes MoW (casterId) — sinon l'AoE du MoW (attacker=casterId)
    # tombe dans le catch-all `damage` au lieu de `dealt`.
    my_ids = [u["id"] for u in units if u.get("team") == my_team]
    my_ids += [m["casterId"] for m in (res.get("mows") or [])
               if m.get("team") == my_team]
    cascade = r.get("cascade") or []
    an = stream_events.analyze(cascade, my_ids)
    _summarize_cascade(an)
    # Diagnostic frontière : TOUT UnitDamaged ciblant un ennemi (capte l'AoE/DoT
    # de fin de tour quelle que soit la source) → vérifie la capture EndTurn.
    enemy_dmg = [d for d in an["damage"] if d.get("target") not in set(my_ids)]
    if enemy_dmg:
        tot = sum(d.get("amount") or 0 for d in enemy_dmg)
        print(f"  DÉGÂTS AUX ENNEMIS (cascade, toutes sources) : "
              f"{len(enemy_dmg)} coups, {tot} dmg")
        for d in enemy_dmg[:14]:
            print("    - " + _fmt_dmg(d))
    return r


def cmd_aiturn(sid: int, a) -> int:
    """Joue UN tour de l'ADVERSAIRE. MÊME GARDE-FOU que cmd_play (l'act-path
    `act endturn` + `aiturn` contournait le fix de cmd_play) : si currentPlayer
    n'est PAS l'ennemi (quirk H19 : le `endturn` ne flippe pas toujours), on
    RE-endturn jusqu'au flip AVANT de jouer — sinon aiPlayByUnit jouerait MA team
    (AI-as-me sur-étend mes units). On REFUSE plutôt que de jouer ma team."""
    st = _load_state()
    rid = st["runnerId"]
    my_team = _my_team(sid, rid, st)
    amine = 3 if my_team == 1 else 4
    aenemy = 4 if my_team == 1 else 3
    cp = _decision(sid, rid).get("currentPlayer")
    if cp != aenemy:
        # pas le tour de l'ennemi -> finir mon tour (endturn) pour lui passer la main.
        flipped = False
        for _ in range(3):
            _rpc(sid, "applyAction",
                 [{"runnerId": rid, "action": {"kind": "endturn"}}], timeout=30)
            if _decision(sid, rid).get("currentPlayer") == aenemy:
                flipped = True
                break
        if not flipped:
            print("  [aiturn] /!\\ impossible de passer la main à l'ennemi (cp reste "
                  "à moi, quirk H19) -> tour IA NON joué (REFUS de jouer MA team). "
                  "Utilise `play` (corrigé) plutôt que act+aiturn.")
            return 2
    _ai_turn(sid, rid, a.maxpump, my_team)
    cp_after = _decision(sid, rid).get("currentPlayer")
    print(f"  [aiturn] terminé -> currentPlayer={cp_after} "
          f"({'à toi' if cp_after == amine else f'inattendu (devrait être {amine})'})")
    return 0


def _ability_reason(sid: int, rid: int, action: dict) -> str:
    """Raison STRUCTURÉE d'un no-op ability (refinement 2) via le RPC `abilityReason`
    → flag `TargetingRule` décodé en noms (hors portée / déjà utilisée / mauvais type
    de cible / LoS / tuile occupée…). '' si indispo. Remplace la devinette du filet."""
    if action.get("kind") != "ability":
        return ""
    body: dict = {"runnerId": rid, "casterId": action.get("casterId"),
                  "abilityType": action.get("abilityType")}
    if action.get("targetId") is not None:
        body["targetId"] = action["targetId"]
    r = (_rpc(sid, "abilityReason", [body], timeout=60).get("result") or {})
    if not r.get("ok"):
        return ""

    def _fmt(rr):
        if not rr:
            return None
        if rr.get("reasons"):
            return ",".join(rr["reasons"])
        rc = rr.get("ruleClass")
        return rc if (rc and rc != "NoBrokenTargetingRule") else None  # None = valide

    bits = []
    # TF24 : la couche targeting IGNORE le cooldown (aucun flag dans TargetingRule)
    # -> casterReason rend ValidRequest même cooldown-locked. L'état LIVE de
    # l'ability (abilityState) est le SEUL signal de dispo réelle.
    ast = r.get("abilityState") or {}
    cd = ast.get("cooldown")
    if cd:
        bits.append(f"COOLDOWN {cd} tour(s) restant(s) (indispo)")
    elif ast.get("disabled"):
        bits.append("ability DÉSACTIVÉE ce tour")
    elif ast.get("usable") is False:
        bits.append("indispo (usable=false)")
    tr, cr = _fmt(r.get("targetReason")), _fmt(r.get("casterReason"))
    if tr:
        bits.append("cible exige: " + tr)
    if cr:
        bits.append("caster: " + cr)
    return (" | RAISON [" + " ; ".join(bits) + "]") if bits else ""


def _tile_set(entries) -> set:
    """{(col,row)} des cibles-TUILE d'une entrée abilityTargets (each t['tile']={col,row})."""
    out = set()
    for t in (entries or []):
        ti = t.get("tile") or {}
        if ti.get("col") is not None:
            out.add((ti.get("col"), ti.get("row")))
    return out


def _ability_prevalidate(sid: int, rid: int, action: dict) -> str:
    """Pré-validation (H55 + TF16) : AVANT applyAction, vérifie que le cast est LÉGAL
    depuis la position COURANTE. Renvoie une raison structurée si ILLÉGAL ce tour sans
    bouger, sinon ''. DEUX chemins selon le type de cible :
      - cible ENTITÉ (targetId) → RPC `abilityReason` (GetInvalidTargetReason, IEntity).
      - cible TILE (`to` hex : bombard / ligne à axe fixe / summon / displace) → RPC
        `abilityTargets` (énumère les TUILES valides now/+move). `abilityReason` ne gère
        QUE les entités → SANS ce volet, une ability hex hors-axe/hors-portée/sans
        spawn-tile no-op SILENCIEUSEMENT (action consommée, activation gaspillée — TF16).
    Laisse passer (fallback réactif) si la query est indispo."""
    caster = action.get("casterId")
    ab = action.get("abilityType")
    tgt = action.get("targetId")
    to = action.get("to")
    if tgt is not None:
        body = {"runnerId": rid, "casterId": caster, "abilityType": ab, "targetId": tgt}
        r = (_rpc(sid, "abilityReason", [body], timeout=60).get("result") or {})
        if not r.get("ok"):
            return ""
        # TF24 : cooldown/disabled pré-rejetés (la couche targeting les ignore et
        # rendrait ValidRequest -> cast no-op silencieux, activation gaspillée).
        ast = r.get("abilityState") or {}
        if ast.get("cooldown"):
            return (f"ability en COOLDOWN ({ast['cooldown']} tour(s) restant(s)) -> "
                    "indispo ce tour (cf. TF24) ; planifie autour du downtime")
        if ast.get("disabled"):
            return "ability DÉSACTIVÉE ce tour -> indispo (cf. TF24)"
        tr = r.get("targetReason") or {}
        if tr.get("reasons"):
            return ("cast ILLÉGAL ce tour sans bouger -> " + ",".join(tr["reasons"])
                    + " ; déplace d'abord ? cf. `abilities` (now/+move)")
        rc = tr.get("ruleClass")
        if rc and rc != "NoBrokenTargetingRule":
            return f"cast ILLÉGAL -> {rc} (cf. `abilities`)"
        return ""
    if to is not None and caster is not None and ab is not None:
        # TF16 : ability TILE-targetée — vérifie la tuile demandée contre le set de
        # tuiles valides d'abilityTargets (now = sans bouger / +move = après déplacement).
        col, row = to.get("col"), to.get("row")
        r = (_rpc(sid, "abilityTargets",
                  [{"runnerId": rid, "unitId": caster, "abilityType": ab}],
                  timeout=120).get("result") or {})
        if not r.get("ok") or not r.get("fromHereResolved"):
            return ""  # fallback réactif
        for u in (r.get("units") or []):
            if u.get("unitId") != caster:
                continue
            for abent in (u.get("abilities") or []):
                if abent.get("abilityId") != ab:
                    continue
                here, allt = _tile_set(abent.get("fromHere")), _tile_set(abent.get("targets"))
                want = (col, row)
                if want in here:
                    return ""  # légal now
                if want in allt:
                    return (f"hex ({col},{row}) atteignable seulement +move (pas castable "
                            f"sans bouger) -> déplace u{caster} d'abord")
                cand = sorted(here or allt)[:6]
                return (f"hex ({col},{row}) HORS des tuiles valides de cette ability "
                        f"(axe de ligne / portée / spawn-tile non libre) -> "
                        f"tuiles légales: {cand or '∅ (aucune ce tour)'}")
            break
    return ""


def _ability_had_real_effect(act: dict) -> bool:
    """True si l'ability a RÉSOLU un effet réel — distingue un actif LÉGITIMEMENT
    non-turn-ending qui a agi (JakhalStimms = dégât, WarHowl = buff/ReceiveEffect ;
    `actionConsumed=False` NORMAL, le caster garde son activation) d'un VRAI no-op
    (cast échoué : seulement le marqueur `User_UseAbility`, rien d'autre). TF29 = le
    faux-positif symétrique du backstop TF12. Signaux d'effet réel : mutation pos/hp,
    summon (`spawned`), OU un event de cascade SIGNIFICATIF (UnitDamaged / ReceiveEffect
    / RemoveUnit) — un no-op n'en émet AUCUN."""
    if act.get("mutated") or act.get("spawned"):
        return True
    meaningful = {"UnitDamaged", "ReceiveEffect", "RemoveUnit"}
    for ev in (act.get("events") or []):
        if stream_events.step_name(ev.get("step")) in meaningful:
            return True
    return False


def _action_failed(r: dict, kind: str, sid: int | None = None,
                   rid: int | None = None, action: dict | None = None) -> str | None:
    """Raison si l'action a ÉCHOUÉ (-> STOPPER le tour AVANT l'endturn, sinon il
    est donné gratis à l'IA), sinon None. ÉCHEC =
      - apply en erreur : ok=False / error / RPC mort               [tous les kinds]
      - un MOVE sans AUCUN effet associé : ni déplacement (mutated/changes), ni
        event de cascade (eventCount==0) = no-op (tuile invalide/bloquée).
      - une ABILITY sans AUCUN event (mutated=False ET eventCount==0) = no-op
        (hors portée / cooldown / munitions / cible invalide). Un vrai buff/marque/
        différée émet >=1 event de cascade -> eventCount==0 = rien n'a firé.
    NB (vérifié internals.ts) : `mutated` = diff de signature pos+hp seulement ; un
    déplacement => mutated=True ; un effet/buff (hors sig pos+hp) => >=1 event. `finish`
    (pas d'effet board) n'avorte QUE sur ok=False / error."""
    if not r.get("ok") and not r.get("actions"):
        return f"RPC échec: {r.get('error') or r}"
    for act in (r.get("actions") or []):
        if act.get("ok") is False or act.get("error"):
            return f"ok={act.get('ok')}" + (
                f" err={act.get('error')}" if act.get("error") else "")
        if (kind == "move" and act.get("mutated") is False
                and not act.get("changes") and not act.get("eventCount")):
            return ("move sans aucun effet (pos inchangée, 0 event) "
                    "-> tuile invalide / bloquée / hors portée ? (cf. `moves`)")
        # TF12 : un cast qui n'a PAS consommé l'activation du caster
        # (actionConsumed=False) ET n'a produit AUCUN effet réel = NO-OP moteur
        # silencieux. Ex. Abraxas MasterOfTheTutelaries : émet `User_UseAbility`
        # (donc eventCount>=1, le filet ci-dessous le RATE) mais ne summon rien et
        # laisse Abraxas « à activer » (typiquement tuile de spawn hors `now`).
        # TF29 (faux-positif symétrique) : un actif LÉGITIMEMENT non-turn-ending qui
        # A RÉSOLU (JakhalStimms = dégât, WarHowl = buff) a AUSSI actionConsumed=False
        # mais GARDE son activation à dessein -> NE PAS l'abandonner : `_ability_had_
        # real_effect` le distingue (dmg/effet/spawn/mutation = a résolu -> on continue).
        if (kind == "ability" and act.get("actionConsumed") is False
                and not _ability_had_real_effect(act)):
            msg = ("ability NON enregistrée comme action ET sans effet réel (caster "
                   f"garde son activation, spawned={act.get('spawned', 0)}, 0 dmg/effet) "
                   "-> NO-OP moteur silencieux (ex. Abraxas MasterOfTheTutelaries : "
                   "summon non déclenché — tuile de spawn hors `now` ? cf. TF12). "
                   "Choisis une AUTRE action / tuile pour ce caster")
            if sid is not None and rid is not None and action is not None:
                msg += _ability_reason(sid, rid, action)
            return msg
        # H55 (volet ability) : une ability sans AUCUN event = vrai no-op (un buff/
        # marque/différée émet >=1 event de cascade) -> hors portée / cooldown /
        # munitions / cible invalide. Distinct de mutated (un buff ne change pas pos+hp).
        if (kind == "ability" and act.get("mutated") is False
                and not act.get("eventCount")):
            msg = ("ability sans aucun effet (mutated=false, 0 event) -> hors portée / "
                   "cooldown / munitions épuisées / cible invalide ? cf. l'état live des "
                   "actifs (prêt/cdN/munitions) dans `view`")
            if sid is not None and rid is not None and action is not None:
                msg += _ability_reason(sid, rid, action)
            return msg
    return None


def _normal_ability_map(res: dict) -> dict:
    """{unitId: id de l'attaque NORMALE concrète} depuis un decisionView (abilities
    kind='normal'). TF18 : l'attaque normale est un ActiveAbilityType PAR UNITÉ (id 69
    n'est PAS universel) → résoudre `{"kind":"normal",...}` sans deviner l'id ni se
    fier au défaut (qui peut résoudre vers un ACTIF)."""
    out: dict = {}
    for u in (res.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal":
                out[u.get("id")] = ab.get("id")
                break
    return out


def _ability_action(ac: dict, plan_ab: dict) -> tuple:
    """Construit l'action 'ability' depuis une entree de spec, ROBUSTE aux abilities
    TARGET-LESS (summon/self-buff) et HEX (`to`) — fix du KeyError 'target' (seed 70000).
    Retourne (action|None, label, err|None). Auto-resout l'id depuis le plan UNIQUEMENT
    si une cible ennemie (`target`) est donnee ; pour summon/self-buff/hex -> 'ability' requis."""
    caster, tgt, to, ab = ac.get("caster"), ac.get("target"), ac.get("to"), ac.get("ability")
    if ab is None:
        ab = plan_ab.get((caster, tgt)) if tgt is not None else None
    if ab is None:
        return None, "", (f"ability u{caster}: passe 'ability':<N> "
                          f"(pas de plan auto sans cible ennemie ; obligatoire summon/self-buff/hex)")
    action = {"kind": "ability", "casterId": caster, "abilityType": ab}
    if tgt is not None:
        action["targetId"] = tgt
        return action, f"ABILITY {ab} u{caster}->u{tgt}", None
    if to is not None:
        if not (isinstance(to, (list, tuple)) and len(to) == 2):
            return None, "", f"ability u{caster}: 'to' doit etre [col,row], recu {to!r}"
        action["to"] = {"col": int(to[0]), "row": int(to[1])}
        return action, f"ABILITY {ab} u{caster}->hex({to[0]},{to[1]})", None
    # target-less (self-buff) : le hook tentera casterId+abilityType ; s'il EXIGE une
    # cible il renverra ok=False (gere par _action_failed) -> PAS un crash Python.
    return action, f"ABILITY {ab} u{caster} (self/target-less)", None


def _movable_map(sid: int, rid: int):
    """{unitId: set((col,row))} des tuiles JOUABLES par unité du joueur courant
    (via aiMovableTiles). Sert à PRÉ-VALIDER les moves AVANT applyAction et à donner
    une RAISON précise au lieu d'un no-op silencieux (H55 : move hors-portée/bloqué =
    moteur ok=true mutated=false SANS raison). Retourne None si l'appel échoue
    -> on saute la pré-validation (fallback sur la détection post-hoc)."""
    r = (_rpc(sid, "aiMovableTiles", [{"runnerId": rid}], timeout=60).get("result") or {})
    units = r.get("units")
    if not units:
        return None
    out: dict = {}
    for u in units:
        uid = u.get("unitId")
        if uid is None:
            continue
        out[uid] = {(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])
                    if t.get("col") is not None and t.get("row") is not None}
    return out


def cmd_play(sid: int, a) -> int:
    """1 ROUND : applique MES actions (--spec JSON), endturn, tour IA, status,
    puis ré-affiche la carte. spec = liste d'actions ; FORMATS EXACTS :
      {"kind":"move","unit":95,"to":[3,2]}   <- 'to' = ARRAY [col,row], jamais "3,2"
      {"kind":"ability","caster":97,"target":89[,"ability":N]}  (ability auto-résolu)
      {"kind":"normal","unit":95,"target":89}  <- attaque NORMALE, id résolu par l'outil
                                                   (TF18 ; ne JAMAIS deviner 69)
      {"kind":"finish","unit":95}
    GARDE anti-no-op : si une action échoue / ne mute pas l'état, on STOPPE
    AVANT l'endturn (échec BRUYANT, l'IA ne joue pas) -> corrige et relance."""
    st = _load_state()
    rid, bc = st["runnerId"], st["bc"]
    st.setdefault("action_log", [])  # séquence live des actions jouées (prefix_log du guard)
    spec = json.loads(a.spec) if a.spec else []
    if not spec:
        print("  [play] spec VIDE -> aucune action, endturn NON joué (passe "
              "des actions, ou `act endturn` si tu veux vraiment finir le tour)")
        return 2
    res = _decision(sid, rid)
    my_ids = [u["id"] for u in (res.get("units") or []) if u.get("ctrl")]
    plan_ab = _plan_ab_map(res)  # {(caster,target): abilityId} depuis les plans
    # TF18 : id de l'attaque NORMALE concrète par unité (NormalAttackType, ≠ 69
    # universel) → permet `{"kind":"normal","unit":N,"target":T}` sans deviner l'id
    # ni risquer que le défaut résolve vers un ACTIF. Lu depuis l'ability kind="normal".
    normal_ab = _normal_ability_map(res)
    # H55 — pré-validation des moves : un move hors-portée/bloqué/déjà-agi est un
    # NO-OP SILENCIEUX côté moteur (ok=true, mutated=false, AUCUNE raison). On calcule
    # le movable set (1 RPC/tour, seulement s'il y a un move dans le spec) pour rejeter
    # AVANT applyAction, avec une raison précise + des tuiles légales.
    movable = _movable_map(sid, rid) if any(ac.get("kind") == "move" for ac in spec) else None
    aborted = None  # raison d'abandon du tour (None = tout OK -> endturn)
    for ac in spec:
        k = ac["kind"]
        if k == "move":
            to = ac.get("to")
            if not (isinstance(to, (list, tuple)) and len(to) == 2):
                aborted = (f"move u{ac.get('unit')}: 'to' doit être [col,row] "
                           f"(array de 2 entiers), reçu {to!r}"); break
            try:
                col, row = int(to[0]), int(to[1])
            except (TypeError, ValueError):
                aborted = (f"move u{ac.get('unit')}: 'to'={to!r} non entier "
                           f"-> [col,row] attendu"); break
            if movable is not None:  # H55 : raison précise AVANT le no-op silencieux
                mv = movable.get(ac["unit"])
                if not mv:
                    aborted = (f"move u{ac['unit']}: AUCUNE tuile jouable ce tour "
                               f"(déjà agi / non contrôlée / morte ?) — cf. 'À ACTIVER' dans `view`")
                    break
                if (col, row) not in mv:
                    near = sorted(mv, key=lambda t: abs(t[0] - col) + abs(t[1] - row))[:8]
                    aborted = (f"move u{ac['unit']}->({col},{row}) HORS du movable set "
                               f"(hors portée / tuile bloquée). Tuiles légales proches: {near}")
                    break
            action = {"kind": "move", "unitId": ac["unit"],
                      "to": {"col": col, "row": row}}
            label = f"MOVE u{ac['unit']}->({col},{row})"
        elif k == "ability":
            action, label, err = _ability_action(ac, plan_ab)
            if err:
                aborted = err; break
            pv = _ability_prevalidate(sid, rid, action)
            if pv:
                aborted = f"{label} -> {pv}"; break
        elif k == "normal":
            caster = ac.get("unit")
            nid = normal_ab.get(caster)
            if nid is None:
                aborted = (f"normal u{caster}: attaque normale non résolue (pas d'ability "
                           f"kind=normal — u{caster} contrôlée/vivante ?)"); break
            if ac.get("target") is None and ac.get("to") is None:
                aborted = (f"normal u{caster}: passe 'target':<id ennemi> (ou 'to':[col,row]) "
                           f"— une attaque normale a besoin d'une cible"); break
            action, _lbl, err = _ability_action(
                {"caster": caster, "target": ac.get("target"),
                 "to": ac.get("to"), "ability": nid}, plan_ab)
            if err:
                aborted = err; break
            label = (f"NORMAL({nid}) u{caster}->u{ac.get('target')}"
                     if ac.get("target") is not None
                     else f"NORMAL({nid}) u{caster}->hex{tuple(ac.get('to'))}")
            pv = _ability_prevalidate(sid, rid, action)
            if pv:
                aborted = f"{label} -> {pv}"; break
        elif k == "finish":
            action = {"kind": "finish", "unitId": ac["unit"]}
            label = f"FINISH u{ac['unit']}"
        else:
            aborted = f"kind inconnu: {k!r} (attendu move|ability|normal|finish)"; break
        r = (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
                  timeout=60).get("result") or {})
        _print_apply(label, r, my_ids)
        fail = _action_failed(r, "ability" if k == "normal" else k, sid, rid, action)
        if fail:
            aborted = f"{label} -> {fail}"; break
        # action RÉUSSIE -> log live (pour replay-to-state du guard). Per-action +
        # save : robuste aux tours splittés sur plusieurs `play` (un re-send d'une
        # action déjà jouée échoue côté engine -> pas re-loggé, pas de doublon).
        st["action_log"].append(action)
        _save_state(st)
    if aborted is not None:
        # TF25 : une action PRÉCÉDENTE du spec a pu DÉJÀ terminer le match (un kill
        # final → FinishMatch) → l'action suivante échoue « stage Finished » : ce n'est
        # PAS un tour abandonné mais une fin de match. On lit le stage autoritatif avant
        # d'alarmer, pour ne pas afficher « TOUR ABANDONNÉ » sur une VICTOIRE.
        bs = (_rpc(sid, "battleStatus", [{"runnerId": rid}], timeout=10)
              .get("result") or {})
        if bs.get("stage") == 2:
            w = bs.get("winner")
            wteam = _winner_label(w)
            st["action_log"].append({"kind": "endturn"})  # marqueur fin de trajectoire
            _save_state(st)
            print(f"  [play] *** MATCH DÉJÀ TERMINÉ — winner AUTORITATIF = {wteam} "
                  f"(battleStatus.winner={w}). L'action suivante « {aborted} » est "
                  f"arrivée APRÈS la fin du match (rien à abandonner). ***")
            return cmd_status(sid, a)
        print(f"  [play] /!\\ TOUR ABANDONNÉ (endturn NON joué, l'IA ne joue "
              f"PAS) : {aborted}")
        print("  -> corrige l'action puis relance `play` ; les actions déjà "
              "appliquées AVANT l'échec sont conservées, rien n'a été donné à l'IA.")
        return 2
    my_team = _my_team(sid, rid, st)
    # NB: player ids != team ids. team 1 <-> player 3 ; team 2 <-> player 4.
    amine = 3 if my_team == 1 else 4
    aenemy = 4 if my_team == 1 else 3

    # FIN DE TOUR — le JEU auto-endturn quand TOUTES mes units ont agi (VÉRIFIÉ
    # empiriquement : finir la dernière unité flip currentPlayer 3->4 tout seul). On
    # NE FORCE PLUS l'endturn après chaque spec : c'était LE bug (un spec PARTIEL
    # forçait la fin -> units restantes jamais jouées, split défait). On lit l'état :
    post = _decision(sid, rid)
    cp = post.get("currentPlayer")
    remaining = post.get("toActivate") or []

    # (1) TOUR PARTIEL non terminé, SANS --end -> le jeu n'a pas flip (units restantes).
    # On NE force PAS : le tour CONTINUE (l'agent rejoue le reste, OU finit exprès).
    if cp == amine and remaining and not a.end:
        print(f"  [play] tour PAS terminé : il reste {len(remaining)} unité(s) à "
              f"activer: {remaining}.")
        print("  -> relance `play` avec leurs actions, OU `play --end` / `act endturn` "
              "si tu as FINI ton tour (réserve délibérée, même partielle).")
        return cmd_status(sid, a)

    # (2) Sinon le tour DOIT se terminer. Marqueur de fin pour la trajectoire (replay).
    st["action_log"].append({"kind": "endturn"})
    _save_state(st)
    # (2a) cp==aenemy déjà : le JEU a auto-endturn (toutes units ont agi) -> rien à forcer.
    # (2b) cp==amine : soit --end (fin délibérée), soit toActivate vide non-flippé (quirk
    #      Ambush/preview de DÉBUT) -> on force l'endturn jusqu'au flip (anti-quirk H19).
    #      Forcer quand cp==amine finit MON tour (ne skippe PAS le tour adverse). NE jamais
    #      lancer _ai_turn tant que cp==amine (sinon l'IA jouerait MA team = carnage 70050).
    if cp != aenemy:
        flipped, stage = False, 1
        for _ in range(3):
            et = (_rpc(sid, "applyAction",
                       [{"runnerId": rid, "action": {"kind": "endturn"}}],
                       timeout=30).get("result") or {})
            stage = et.get("stage", 1)
            if stage != 1:
                print("  *** battle finie après mon tour ***")
                return cmd_status(sid, a)
            if _decision(sid, rid).get("currentPlayer") == aenemy:
                flipped = True
                break
        if not flipped:
            print("  [play] /!\\ endturn n'a pas flippé sur l'ennemi (quirk H19) -> "
                  "tour IA NON joué. NE lance PAS `aiturn` manuel ; relance `play` ou "
                  "investigue.")
            return cmd_status(sid, a)
    # SELF-PLAY (--no-ai) : mon tour est fini, la main est passée à l'adversaire
    # (currentPlayer=aenemy garanti par le flip ci-dessus). On NE joue PAS le tour
    # IA natif : c'est à l'AUTRE agent oracle de jouer l'autre camp (il attend son
    # tour via l'endpoint host /api/selfplay/:id/await). cf. docs/rl/design.md.
    if getattr(a, "no_ai", False):
        cp_after = _decision(sid, rid).get("currentPlayer")
        ok = cp_after == aenemy
        print(f"  [play --no-ai] tour fini -> main passée à l'adversaire "
              f"(currentPlayer={cp_after}"
              + ("=adversaire, OK" if ok else f", attendu {aenemy} /!\\")
              + "). AUCUN tour IA natif joué (self-play : à l'autre agent de jouer).")
        return cmd_status(sid, a)
    # Tour de l'IA (cp==ennemi garanti -> aiPlayByUnit joue bien l'ADVERSAIRE).
    _ai_turn(sid, rid, a.maxpump, my_team)
    cp_after = _decision(sid, rid).get("currentPlayer")
    note = ("à toi — le tour IA est DÉJÀ joué, NE lance PAS `aiturn`"
            if cp_after == amine else
            f"/!\\ currentPlayer={cp_after} inattendu (devrait être {amine}=moi)")
    print(f"  [round terminé] currentPlayer={cp_after} ({note})")
    # Bilan + carte pour ma prochaine décision.
    print("\n========== ÉTAT APRÈS LE ROUND ==========")
    cmd_status(sid, a)
    res2 = _decision(sid, rid)
    if res2.get("ok"):
        print()
        print(oracle.build_card(res2, Board(bc), round_cap=_env_bombardment_cap(bc),
                                pov_team=st.get("myTeam"), turn_no=_turn_no(st)))
    return 0


def cmd_status(sid: int, a) -> int:
    st = _load_state()
    rid = st["runnerId"]
    res = _decision(sid, rid)
    units = res.get("units") or []
    alive = _alive_by_team(units)
    # H59 — battleStatus expose le champ winner NATIF (lisible AUSSI post-Finished tant
    # que l'entité Match n'est pas purgée). decisionView REFUSE hors-Running -> ses units
    # sont vides -> alive={} ne distingue PAS une élimination d'un no-winner round-cap.
    # Le winner natif tranche : playerId 3=team1 / 4=team2, 0=aucun (no-winner / en cours).
    bs = (_rpc(sid, "battleStatus", [{"runnerId": rid}], timeout=10).get("result") or {})
    stage = bs.get("stageName") or res.get("stageName")
    print(f"[status] stage={stage} turn={res.get('turn')} "
          f"currentPlayer={res.get('currentPlayer') or bs.get('currentPlayer')} "
          f"alive_by_team={alive}")
    for u in units:
        if u.get("alive"):
            pos = u.get("pos") or {}
            print(f"    t{u.get('team')} u{u.get('id')} [{u.get('visualId')}] "
                  f"@({pos.get('col')},{pos.get('row')}) hp={u.get('hp')} "
                  f"{'CTRL' if u.get('ctrl') else 'AI'}")
    if bs.get("stage") == 2:  # Finished -> vainqueur AUTORITATIF (champ natif)
        w = bs.get("winner")
        wteam = _winner_label(w)
        print(f"  *** BATTLE FINIE — winner AUTORITATIF = {wteam} "
              f"(battleStatus.winner={w}, unitsAlive={bs.get('unitsAlive')}) ***")
    elif len(alive) <= 1 and units:
        win = next(iter(alive), None)
        print(f"  *** BATTLE FINIE (inférée alive) — team={win} ***")
    return 0


def cmd_dispose(sid: int, a) -> int:
    st = _load_state()
    _rpc(sid, "disposeRunner", [{"runnerId": st["runnerId"]}], timeout=15)
    print(f"[dispose] runner {st['runnerId']} libéré")
    return 0


def cmd_attach(sid: int, a) -> int:
    """SELF-PLAY : crée un state-file pour un 2e agent player pointant sur un
    runner DÉJÀ construit (pas de rebuild). Copie {runnerId, bc, seed,
    playerUnits} depuis --from et fixe le camp via --team (1|2 ; omis =
    auto-dérivé du currentPlayer à chaque tour). action_log repart vide (démo
    propre par player). cf. docs/rl/design.md §Self-play."""
    if not a.attach_from:
        print("[attach] --from <state-file source> requis", file=sys.stderr)
        return 2
    src = json.loads(Path(a.attach_from).read_text(encoding="utf-8"))
    rid = a.runner if a.runner is not None else src.get("runnerId")
    if rid is None:
        print("[attach] pas de runnerId (ni --runner ni dans --from)",
              file=sys.stderr)
        return 2
    out = {"runnerId": rid, "bc": src.get("bc"), "seed": src.get("seed"),
           "playerUnits": src.get("playerUnits"), "action_log": []}
    if a.team is not None:
        out["myTeam"] = a.team
    _save_state(out)
    print(f"[attach] {STATE} -> runner {rid} "
          f"team={a.team if a.team is not None else 'auto'}")
    return 0


# ===== GUARD T1 (Phase A) — éval d'une approche par clone-sim, RAPPORT seul =====
# Clone = initAndStart frais (config+playerUnits = déploiement T1 déterministe) ;
# on replay le spec d'approche, endturn, on fait JOUER l'IA (aiPlayByUnit, 1 tour),
# on diff l'état avant/après -> outcome RÉEL (ground truth, lookahead 1-ply). RNG
# combat déterministe (vérifié) -> 1 sim suffit. Score classant NET = leurs_pertes
# − mes_pertes (fraction maxHP perdue + pénalité mort, pondération SIMPLE sans rôle).
# Phase A = RAPPORT (pas de gate, pas de variantes). Ne touche PAS le runner live.
DEATH_PENALTY = 1.0  # mort = frac 1.0 (hp) + 1.0 = 2.0 (corps perdu > chip)


def _snapshot(sid: int, rid: int) -> dict:
    """État unités {id: {hp, team, vis, pos}} via decisionView : diff NET (_score_net)
    + détection de désync du replay du guard (_replay_desync, TF27)."""
    res = _decision(sid, rid)
    out = {}
    for u in (res.get("units") or []):
        p = u.get("pos") or {}
        out[u["id"]] = {"hp": u.get("hp") or 0, "team": u.get("team"),
                        "vis": u.get("visualId"), "pos": (p.get("col"), p.get("row"))}
    return out


def _replay_desync(live: dict | None, clone: dict | None) -> str | None:
    """TF27 — compare le snapshot du CLONE post-replay au snapshot LIVE. Le replay de
    l'action_log est censé reconstruire À L'IDENTIQUE l'état live (RNG déterministe ;
    _enemy_turn 0-diff). S'il DIVERGE (une action live qui no-op silencieusement au
    replay → état périmé, typiquement après plusieurs tours splittés), le guard
    évaluerait une spec sur un état FAUX et rendrait un NET trompeur (≈ constant quelle
    que soit la spec — le symptôme exact de TF27). On le détecte pour ABORT explicitement
    au lieu de rendre une éval invalide. Retourne une raison de divergence, ou None."""
    if not live or not clone:
        return None  # pas de référence live -> pas de check (compat appelants sans live)
    lk, ck = set(live), set(clone)
    if lk != ck:
        miss, extra = sorted(lk - ck)[:4], sorted(ck - lk)[:4]
        return f"set d'unités divergent (live\\clone={miss}, clone\\live={extra})"
    diffs = []
    for uid in lk:
        a, b = live[uid], clone[uid]
        if abs((a.get("hp") or 0) - (b.get("hp") or 0)) > 1:
            diffs.append(f"u{uid} hp {a.get('hp')}≠{b.get('hp')}")
        elif a.get("pos") != b.get("pos"):
            diffs.append(f"u{uid} pos {a.get('pos')}≠{b.get('pos')}")
    return ("état clone≠live: " + ", ".join(diffs[:5])) if diffs else None


def _apply_spec_to(sid: int, rid: int, spec: list) -> tuple:
    """Applique le spec sur rid (clone) SANS endturn. Réutilise la garde
    anti-no-op (_action_failed). Retourne (n_appliquées, raison_abort|None)."""
    res = _decision(sid, rid)
    plan_ab = _plan_ab_map(res)
    normal_ab = _normal_ability_map(res)  # TF18 : id normale concrète par unité
    applied = 0
    for ac in spec:
        k = ac.get("kind")
        if k == "move":
            to = ac.get("to")
            if not (isinstance(to, (list, tuple)) and len(to) == 2):
                return applied, f"move u{ac.get('unit')}: 'to' doit être [col,row], reçu {to!r}"
            try:
                col, row = int(to[0]), int(to[1])
            except (TypeError, ValueError):
                return applied, f"move u{ac.get('unit')}: 'to'={to!r} non entier"
            action = {"kind": "move", "unitId": ac["unit"],
                      "to": {"col": col, "row": row}}
        elif k == "ability":
            action, _label, err = _ability_action(ac, plan_ab)
            if err:
                return applied, err
        elif k == "normal":  # TF18 : attaque normale, id résolu (≠ 69 universel)
            nid = normal_ab.get(ac.get("unit"))
            if nid is None:
                return applied, f"normal u{ac.get('unit')}: attaque normale non résolue"
            action, _label, err = _ability_action(
                {"caster": ac.get("unit"), "target": ac.get("target"),
                 "to": ac.get("to"), "ability": nid}, plan_ab)
            if err:
                return applied, err
        elif k == "finish":
            action = {"kind": "finish", "unitId": ac["unit"]}
        else:
            return applied, f"kind inconnu: {k!r}"
        r = (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
                  timeout=60).get("result") or {})
        fail = _action_failed(r, "ability" if k == "normal" else k, sid, rid, action)
        if fail:
            return applied, f"{k} -> {fail}"
        applied += 1
    return applied, None


def _auto_spec(sid: int, rid: int, mode: str) -> list:
    """Génère un spec de move depuis les movable tiles du runner (objectif, pas
    cherry-pické). 'forward' = vers le centroïde ennemi. hold=[] (rien) ;
    gentle=~+2 rangs vers l'ennemi ; aggressive=tuile la PLUS en avant."""
    if mode == "hold":
        return []
    dv = _decision(sid, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    enemy = [u for u in units if not u.get("ctrl")]

    def crow(us):
        rs = [u["pos"]["row"] for u in us if u.get("pos")]
        return sum(rs) / len(rs) if rs else 0
    fwd = 1 if crow(enemy) > crow(mine) else -1
    pos_by = {u["id"]: (u.get("pos") or {}) for u in mine}
    mv = (_rpc(sid, "aiMovableTiles", [{"runnerId": rid, "side": "friendly"}],
               timeout=60).get("result") or {})
    spec = []
    used = set()  # évite que 2 units visent la même tuile (-> abort collision)
    for um in (mv.get("units") or []):
        tiles = [t for t in (um.get("tiles") or [])
                 if (t["col"], t["row"]) not in used]
        if not tiles:
            continue
        if mode == "aggressive":
            t = max(tiles, key=lambda t: fwd * t["row"])
        else:  # gentle : la tuile la plus proche de current +2 rangs vers l'ennemi
            target = pos_by.get(um["unitId"], {}).get("row", 0) + fwd * 2
            t = min(tiles, key=lambda t: abs(t["row"] - target))
        used.add((t["col"], t["row"]))
        spec.append({"kind": "move", "unit": um["unitId"], "to": [t["col"], t["row"]]})
    return spec


def _score_net(before: dict, after: dict, my_team) -> dict:
    """NET = leurs_pertes − mes_pertes. Perte/unité = frac_maxHP_perdue +
    PÉNALITÉ_MORT×mort (before@T1 = full HP = maxHP). Pondération SIMPLE (pas de
    rôle). Survivants/morts seulement (summons apparus ignorés)."""
    my_loss = their_loss = 0.0
    rows = []
    for uid, b in before.items():
        a_ = after.get(uid)
        maxhp = b["hp"] or 1
        if a_ is None or (a_["hp"] or 0) <= 0:
            died, after_hp, lost_frac = True, 0, 1.0
        else:
            died, after_hp = False, a_["hp"]
            lost_frac = max(0.0, (b["hp"] - after_hp) / maxhp)
        loss = lost_frac + (DEATH_PENALTY if died else 0.0)
        mine = (b["team"] == my_team)
        if mine:
            my_loss += loss
        else:
            their_loss += loss
        if loss > 0.001:
            rows.append({"id": uid, "vis": b["vis"], "mine": mine,
                         "before": b["hp"], "after": after_hp, "died": died,
                         "frac": lost_frac, "loss": loss})
    worst = max((r for r in rows if r["mine"]),
                key=lambda r: r["loss"], default=None)
    return {"net": their_loss - my_loss, "my_loss": my_loss,
            "their_loss": their_loss, "rows": rows, "worst": worst}


MIN_CONTACT = 500  # AI T1 infligeant < ça à mes units = AVANCE (no contact) -> 2-ply


def _my_dmg(before: dict, after: dict, my_team) -> float:
    """Somme des PV perdus par MES units entre 2 snapshots (détecte le contact)."""
    tot = 0.0
    for uid, b in before.items():
        if b["team"] != my_team:
            continue
        a_ = after.get(uid)
        ahp = (a_["hp"] if a_ else 0)
        tot += max(0, (b["hp"] or 0) - ahp)
    return tot


def _sim_plan(sid: int, bc: dict, seed, pu: list, spec: list, my_team,
              maxpump: int, two_ply: bool = True) -> dict:
    """UNE sim isolée : clone T1 (initAndStart, coexist par défaut) -> replay spec ->
    endturn -> l'IA joue 1 tour (1-PLY) -> score NET -> dispose. Ne touche pas le live.
    2-PLY (two_ply, défaut ON) : si le 1er tour IA est une AVANCE (~0 dmg sur mes
    units = pas de contact), pousse la sim d'UN tour de plus (mon HOLD T2 -> AI T2)
    pour capturer le FOCUS RETARDÉ du 2e tour IA que le 1-ply RATE (validé seed 70003 :
    AI T1 = avance 0 dmg, AI T2 = 6525 dmg + 1 kill). NET sur la fenêtre complète. RNG
    déterministe -> 1 sim/plan. Retourne {sc|None, aborted, n, ai, plies}."""
    init = (_rpc(sid, "initAndStart",
                 [{"configJson": json.dumps(bc), "seed": seed,
                   "playerUnits": pu}],
                 timeout=40).get("result") or {})
    rid = init.get("runnerId")
    if rid is None:
        return {"sc": None, "aborted": f"clone init échec: {init}", "n": 0,
                "ai": {}, "plies": 0}

    def _ai_turn():
        return (_rpc(sid, "aiPlayByUnit",
                     [{"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                       "maxPump": maxpump, "captureEvents": True}],
                     timeout=300).get("result") or {})

    try:
        before = _snapshot(sid, rid)
        n, aborted = _apply_spec_to(sid, rid, spec)
        if aborted is not None:
            return {"sc": None, "aborted": aborted, "n": n, "ai": {}, "plies": 0}
        et = (_rpc(sid, "applyAction",
                   [{"runnerId": rid, "action": {"kind": "endturn"}}],
                   timeout=30).get("result") or {})
        ai_player = et.get("currentPlayer")
        ai = _ai_turn()
        after = _snapshot(sid, rid)
        plies = 1
        # 2-PLY conditionnel : 1er tour IA = AVANCE (no contact) -> mon HOLD T2 + AI T2.
        # NB: le résultat aiPlayByUnit expose `finalStage` (numérique : 1 = Running,
        # cf. _advance ligne 99) ET `finalStageName` (string). On teste le numérique
        # (== 1) — comparer le numérique à la string "Running" donnait toujours False
        # et le 2-ply ne firait JAMAIS (bug du verdict 70003 "propre").
        if (two_ply and after and ai.get("finalStage") == 1
                and _my_dmg(before, after, my_team) < MIN_CONTACT):
            if ai.get("finalPlayer") != ai_player:   # remettre la main à l'IA si besoin
                _rpc(sid, "applyAction",
                     [{"runnerId": rid, "action": {"kind": "endturn"}}], timeout=30)
            ai2 = _ai_turn()
            after2 = _snapshot(sid, rid)
            if after2:
                after, ai, plies = after2, ai2, 2
        if before and not after:
            return {"sc": None, "aborted": "état après vide (battle finie ?)",
                    "n": n, "ai": ai, "plies": plies}
        return {"sc": _score_net(before, after, my_team), "aborted": None,
                "n": n, "ai": ai, "plies": plies}
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=15)


def _enemy_turn(sid: int, rid: int, my_team, max_tries: int = 3) -> str | None:
    """Joue UN tour de l'ADVERSAIRE : endturn (mon tour -> l'ennemi) puis
    CheatRunAIMessage ×1 (autoPlayRunner maxTurns:1). GARDE-FOU CRITIQUE : on
    n'appelle autoPlayRunner QUE si l'endturn a flippé sur l'ennemi — sinon
    CheatRunAIMessage jouerait MA team (interdit). Le 1er endturn ne flippe pas
    toujours (quirk H19 : rend la preview IA d'abord) -> on RE-endturn jusqu'à
    flip, max_tries. NE ré-endturn QUE tant que ce n'est pas l'ennemi (sinon on
    finirait le tour de l'ennemi). Retourne une raison d'abort, ou None si OK."""
    aenemy = 4 if my_team == 1 else 3
    flipped = False
    for _ in range(max_tries):
        _rpc(sid, "applyAction",
             [{"runnerId": rid, "action": {"kind": "endturn"}}], timeout=30)
        if _decision(sid, rid).get("currentPlayer") == aenemy:
            flipped = True
            break
    if not flipped:
        cp = _decision(sid, rid).get("currentPlayer")
        return f"endturn n'a pas flippé sur l'ennemi après {max_tries} essais " \
               f"(currentPlayer={cp}) -> abort (ne JAMAIS laisser l'IA jouer ma team)"
    _rpc(sid, "autoPlayRunner", [{"runnerId": rid, "maxTurns": 1}], timeout=300)
    return None


def _replay_log(sid: int, rid: int, prefix_log: list | None, my_team) -> str | None:
    """Rejoue sur le clone la séquence EXACTE des actions live déjà jouées =
    `prefix_log` (actions LIVE-format déjà appliquées + marqueurs {"kind":"endturn"}).
    À chaque endturn -> _enemy_turn (1 tour IA adverse déterministe ; équivalent au
    live : aiPlayByUnit==CheatRunAIMessage VÉRIFIÉ 0-diff). Reconstruit l'état au
    DÉBUT de mon tour courant SANS jamais que l'IA joue ma team. Les actions ayant
    réussi live se ré-appliquent à l'identique (RNG déterministe). Retourne abort|None."""
    for i, item in enumerate(prefix_log or []):
        if item.get("kind") == "endturn":
            ab = _enemy_turn(sid, rid, my_team)
            if ab is not None:
                return f"replay[{i}] endturn: {ab}"
        else:
            r = (_rpc(sid, "applyAction", [{"runnerId": rid, "action": item}],
                      timeout=60).get("result") or {})
            if r.get("ok") is False:
                return f"replay[{i}] {item.get('kind')}: {r.get('error')}"
    return None


def _sim_turn(sid: int, bc: dict, seed, pu: list, spec: list, my_team,
              maxpump: int, prefix_log: list | None = None,
              live_snap: dict | None = None) -> dict:
    """1 SIM (modèle VERROUILLÉ, cf. directive) = [mes moves `spec`] -> endturn ->
    1 tour IA ADVERSE (CheatRunAIMessage via autoPlayRunner maxTurns:1) -> NET.
    JAMAIS plus loin. RÈGLE ABSOLUE : l'IA ne joue QUE l'adversaire ; ma team ne
    fait QUE mes moves explicites (jamais auto-jouée par l'IA — l'IA sur-étend, ça
    biaiserait). Pour évaluer un tour > T1, `prefix_log` = le log des actions live
    déjà jouées (cf. _replay_log) : on le rejoue pour reconstruire l'état courant
    sur le clone T1 (replay-to-state). Retourne {sc, aborted}. NET = before(début
    du tour évalué) -> after(post-IA) = coût net de CE tour."""
    init = (_rpc(sid, "initAndStart",
                 [{"configJson": json.dumps(bc), "seed": seed,
                   "playerUnits": pu}],
                 timeout=40).get("result") or {})
    rid = init.get("runnerId")
    if rid is None:
        return {"sc": None, "aborted": f"clone init échec: {init}"}
    try:
        ab = _replay_log(sid, rid, prefix_log, my_team)
        if ab is not None:
            return {"sc": None, "aborted": ab}
        # --- le tour à ÉVALUER : mes moves -> endturn -> 1 tour IA adverse
        before = _snapshot(sid, rid)
        # TF27 : le clone post-replay DOIT matcher le live ; sinon le replay a désync
        # (une action live no-op'ée) → évaluer la spec dessus rendrait un NET trompeur.
        desync = _replay_desync(live_snap, before)
        if desync is not None:
            return {"sc": None, "aborted": f"replay désync (clone≠live) — {desync}"}
        n, ab = _apply_spec_to(sid, rid, spec)
        if ab is not None:
            return {"sc": None, "aborted": ab}
        ab = _enemy_turn(sid, rid, my_team)
        if ab is not None:
            return {"sc": None, "aborted": ab}
        after = _snapshot(sid, rid)
        return {"sc": _score_net(before, after, my_team), "aborted": None}
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=15)


def _unit_of(act: dict):
    """Unité concernée par une action (move/finish=unit, ability=caster)."""
    return act.get("unit", act.get("caster"))


def _hill_climb(sid: int, bc: dict, seed, pu: list, base_spec: list,
                base_sc: dict, my_team, maxpump: int, max_variants: int,
                prefix_log: list, live_snap: dict | None = None) -> tuple:
    """Greedy BATCHÉ : tant que je ne suis PAS focus-first (NET<0 = l'IA me focus
    avant), retire d'un coup TOUTES mes units MORTES ou ≥50% du sim courant (ground
    truth de la réponse IA d'1 tour) ; à défaut (chip seul) retire le worst. Re-sim
    (_sim_turn, même prefix_log = même tour), garde si NET monte. Le batch coupe les
    itérations sur l'over-extension MULTI-units. Stop si NET>=0 (focus-first atteint) /
    rien de corrigeable (unités touchées hors de mon spec = exposées au déploiement,
    pull impossible) / pas d'amélioration / budget. Greedy conservateur."""
    best_spec, best_sc = base_spec, base_sc
    trail = [("base", best_sc)]
    n = 0
    while n < max_variants:
        if best_sc["net"] >= 0:            # focus-first atteint -> rien à corriger
            break
        # Batch = mes units mortes OU ≥50% (focus RÉEL de ce sim) ; sinon le worst.
        heavy = {r["id"] for r in best_sc["rows"]
                 if r["mine"] and (r["died"] or r["frac"] >= 0.5)}
        if not heavy and best_sc.get("worst"):
            heavy = {best_sc["worst"]["id"]}
        in_spec = {_unit_of(act) for act in best_spec}
        pull = heavy & in_spec
        if not pull:
            break  # units touchées pas dans le spec (exposées au déploiement) -> stop
        variant = [act for act in best_spec if _unit_of(act) not in pull]
        r = _sim_turn(sid, bc, seed, pu, variant, my_team, maxpump, prefix_log,
                      live_snap=live_snap)
        n += 1
        label = "pull " + ",".join(f"u{i}" for i in sorted(pull))
        if r["sc"] is None:
            trail.append((label + " ABORT", None))
            break
        trail.append((label, r["sc"]))
        if r["sc"]["net"] > best_sc["net"] + 1e-6:
            best_spec, best_sc = variant, r["sc"]
        else:
            break  # pas d'amélioration -> stop (greedy)
    return best_spec, best_sc, trail, n


def _sc_line(sc: dict, hold_net: float) -> str:
    w = sc.get("worst")
    if not w:
        wtxt = "-"
    else:
        wtxt = (f"u{w['id']}[{w['vis']}] "
                + ("MORT" if w["died"] else f"{w['frac']*100:.0f}%"))
    return (f"NET {sc['net']:+.2f} (delta {sc['net']-hold_net:+.2f}) | "
            f"worst={wtxt} | pertes moi {sc['my_loss']:.2f} eux {sc['their_loss']:.2f}")


def _print_losses(sc: dict) -> None:
    mine = sorted((r for r in sc["rows"] if r["mine"]), key=lambda r: -r["loss"])
    theirs = sorted((r for r in sc["rows"] if not r["mine"]), key=lambda r: -r["loss"])
    if mine:
        print("  MES PERTES:")
        for r in mine:
            tag = "MORT" if r["died"] else f"{r['frac']*100:.0f}% max"
            w = "  <- worst" if r is sc["worst"] else ""
            print(f"    u{r['id']} [{r['vis']}] {r['before']}->{r['after']} {tag}{w}")
    if theirs:
        print("  LEURS PERTES:")
        for r in theirs:
            tag = "MORT" if r["died"] else f"{r['frac']*100:.0f}%"
            print(f"    u{r['id']} [{r['vis']}] {r['before']}->{r['after']} {tag}")


def _verdict(sc: dict, hold_net: float) -> None:
    """Verdict sur le DELTA NET(plan)−NET(hold) (calibré : un board serré expose
    déjà au déploiement -> le delta isole le coût MARGINAL de l'agressivité)."""
    delta = sc["net"] - hold_net
    heavy = any(r["mine"] and (r["died"] or r["frac"] >= 0.5) for r in sc["rows"])
    if heavy and sc["net"] >= 0:
        print(f"  VERDICT: perte/quasi-perte MAIS NET>=0 -> trade/bait OK (delta {delta:+.2f})")
    elif heavy or delta <= -1.0:
        print(f"  VERDICT: OVER-EXTENDED (perte/quasi-perte ou delta<=-1.0 ; delta {delta:+.2f})")
    elif delta < -0.1:
        print(f"  VERDICT: exposition modérée -> caution (delta {delta:+.2f})")
    else:
        print(f"  VERDICT: approche propre (delta {delta:+.2f})")


def cmd_guard(sid: int, a) -> int:
    """Gate anti-over-extension PER-TURN. Évalue mon spec du TOUR COURANT via
    _sim_turn (mes moves -> endturn -> 1 tour IA ADVERSE -> NET ; l'IA ne joue
    JAMAIS ma team). Reconstruit le tour courant en rejouant st['action_log']
    (replay-to-state) -> marche à T1 COMME aux tours suivants : à appeler AVANT
    CHAQUE `play`. NET<0 = l'IA me focus AVANT moi = over-extension ; NET>=0 =
    focus-first. --climb : pull-back des units sur-étendues jusqu'au focus-first
    (NET>=0) ou --cap sims. Spec via --spec ou --auto. Live JAMAIS muté (clone)."""
    st = _load_state()
    bc, seed, my_team = st["bc"], st["seed"], st.get("myTeam")
    pu, live_rid = st.get("playerUnits"), st.get("runnerId")
    prefix_log = st.get("action_log", [])
    if not pu:
        print("[guard] playerUnits absent -> rebuild requis (build le sauve)",
              file=sys.stderr)
        return 2
    if getattr(a, "auto", None):
        base_spec = _auto_spec(sid, live_rid, a.auto)  # généré sur le live (read-only)
        mode = a.auto
    else:
        base_spec = json.loads(a.spec) if a.spec else []
        if not base_spec:
            print("[guard] spec VIDE (ou --auto hold|gentle|aggressive)", file=sys.stderr)
            return 2
        mode = "spec"
    cap = max(2, getattr(a, "cap", None) or 5)
    do_climb = bool(getattr(a, "climb", False))
    turn_no = sum(1 for x in prefix_log if x.get("kind") == "endturn") + 1
    # TF27 : réf. de l'état LIVE pour détecter un replay désync (clone≠live → NET
    # trompeur). Capturé UNE fois sur le runner live, comparé après chaque replay.
    live_snap = _snapshot(sid, live_rid) if live_rid is not None else None

    # baseline hold (ce tour) + plan de base, reconstruits au tour courant via replay.
    hold_r = _sim_turn(sid, bc, seed, pu, [], my_team, a.maxpump, prefix_log,
                       live_snap=live_snap)
    if hold_r["sc"] is None:
        print(f"[guard] hold abort: {hold_r['aborted']}", file=sys.stderr)
        return 2
    hold_net = hold_r["sc"]["net"]
    base_r = _sim_turn(sid, bc, seed, pu, base_spec, my_team, a.maxpump, prefix_log,
                       live_snap=live_snap)
    if base_r["sc"] is None:
        print(f"[guard] plan base abort: {base_r['aborted']}", file=sys.stderr)
        return 2
    sims = 2
    base_sc = base_r["sc"]

    if not do_climb:
        print(f"\n=== GUARD tour {turn_no} [{mode}] (mes moves -> 1 tour IA adverse, {sims} sims) ===")
        print(f"  baseline hold : NET {hold_net:+.2f}")
        print(f"  plan          : {_sc_line(base_sc, hold_net)}")
        _print_losses(base_sc)
        _verdict_focus(base_sc, hold_net)
        return 0

    best_spec, best_sc, trail, extra = _hill_climb(
        sid, bc, seed, pu, base_spec, base_sc, my_team, a.maxpump,
        max_variants=cap - sims, prefix_log=prefix_log, live_snap=live_snap)
    sims += extra
    print(f"\n=== GUARD tour {turn_no} [{mode}, CLIMB] ({sims} sims) ===")
    print(f"  baseline hold : NET {hold_net:+.2f}")
    for label, sc in trail:
        print(f"  {label:14s}: {'ABORT' if sc is None else _sc_line(sc, hold_net)}")
    print(f"  >>> MEILLEUR  : {_sc_line(best_sc, hold_net)}")
    if best_spec != base_spec:
        n_pull = len(base_spec) - len(best_spec)
        print(f"  >>> pull-back appliqué ({n_pull} action(s) retirée(s)) ; "
              f"spec recommandé : {json.dumps(best_spec)}")
    else:
        print("  >>> plan base déjà optimal (aucun pull-back n'améliore)")
    _print_losses(best_sc)
    _verdict_focus(best_sc, hold_net)
    return 0


def _verdict_focus(sc: dict, hold_net: float) -> None:
    """Verdict sur le NET du tour évalué (modèle verrouillé = mes moves -> endturn
    -> 1 tour IA adverse). NET = leurs_pertes − mes_pertes sur CE tour : NET<0 =
    l'IA m'a out-tradé ce tour = l'IA focus AVANT moi = over-extension. NET>=0 =
    je tiens / je gagne l'échange (focus-first). delta vs hold = coût marginal de
    mon move (en enemy-only 1-tour il N'y a PAS de self-play qui rescue, donc le
    delta isole bien le move)."""
    net, delta = sc["net"], sc["net"] - hold_net
    if net >= 0.5:
        print(f"  VERDICT: FOCUS-FIRST — je gagne l'échange (NET {net:+.2f}, delta {delta:+.2f})")
    elif net > -0.5:
        print(f"  VERDICT: échange SERRÉ/neutre — caution (NET {net:+.2f}, delta {delta:+.2f})")
    else:
        print(f"  VERDICT: l'IA focus AVANT moi -> OVER-EXTENDED / position perdante "
              f"(NET {net:+.2f}, delta {delta:+.2f})")


def cmd_rollout(sid: int, a) -> int:
    """TEST de l'évaluateur `_sim_turn` (modèle VERROUILLÉ : mes moves -> endturn ->
    1 tour IA adverse via CheatRunAIMessage -> NET ; jamais plus loin, l'IA ne joue
    JAMAIS ma team). Calcule NET(hold) baseline + NET(spec) + delta + verdict focus.
    Spec via --spec ou --auto (--auto a besoin d'un runner live dans le state)."""
    st = _load_state()
    bc, seed, my_team = st["bc"], st["seed"], st.get("myTeam")
    pu, live_rid = st.get("playerUnits"), st.get("runnerId")
    prefix_log = st.get("action_log", [])
    if not pu:
        print("[rollout] playerUnits absent -> rebuild requis", file=sys.stderr)
        return 2
    if a.auto:
        spec, mode = _auto_spec(sid, live_rid, a.auto), a.auto
    else:
        spec = json.loads(a.spec) if a.spec else []
        mode = "spec" if spec else "hold-only"

    live_snap = _snapshot(sid, live_rid) if live_rid is not None else None  # TF27 désync ref
    hold = _sim_turn(sid, bc, seed, pu, [], my_team, a.maxpump, prefix_log,
                     live_snap=live_snap)
    if hold["sc"] is None:
        print(f"[rollout] hold abort: {hold['aborted']}", file=sys.stderr)
        return 2
    hold_net = hold["sc"]["net"]
    turn_no = sum(1 for x in prefix_log if x.get("kind") == "endturn") + 1
    print(f"\n=== SIM tour {turn_no} (mes moves -> endturn -> 1 tour IA adverse, maxPump {a.maxpump}) ===")
    print(f"  HOLD : NET {hold_net:+.2f}")
    if spec:
        plan = _sim_turn(sid, bc, seed, pu, spec, my_team, a.maxpump, prefix_log,
                         live_snap=live_snap)
        if plan["sc"] is None:
            print(f"  PLAN : ABORT {plan['aborted']}", file=sys.stderr)
            return 2
        ps = plan["sc"]
        print(f"  PLAN [{mode}] : {_sc_line(ps, hold_net)}")
        _print_losses(ps)
        _verdict_focus(ps, hold_net)
    return 0


def cmd_verdict(sid: int, a) -> int:
    """TF02 — VERDICT de position : matériel (HP + unités par équipe) + létalité estimée
    CE TOUR (cibles K! dans mes plans) + un flag `decided: won|lost|undecided` à PRUDENCE
    ASYMÉTRIQUE — 'won' n'est déclaré qu'à élimination adverse (contre la sur-estimation
    « je gagne » de TF02) ; 'lost' peut s'avancer en early-warning. Aide à décider
    l'abandon sans compter HP/unités à la main chaque tour."""
    st = _load_state()
    rid, my_team = st["runnerId"], st.get("myTeam")
    bs = (_rpc(sid, "battleStatus", [{"runnerId": rid}], timeout=10).get("result") or {})
    if bs.get("stage") == 2:  # match fini → winner autoritatif
        w = bs.get("winner")
        wteam = _winner_team(w)
        flag = "won" if (my_team is not None and wteam == my_team) else "lost"
        tag = "no-winner (double-wipe round-cap)" if w in (0, None) else f"team{wteam}"
        print(f"[verdict] decided={flag} · BATTLE FINIE — winner autoritatif={tag}")
        return 0
    res = _decision(sid, rid)
    units = [u for u in (res.get("units") or []) if u.get("alive")]
    if not units:
        print("[verdict] decided=undecided · aucune unité vivante lisible (état douteux)")
        return 0
    if my_team is None:
        my_team = next((u.get("team") for u in units if u.get("ctrl")), None)
    teams: dict = {}
    for u in units:
        d = teams.setdefault(u.get("team"), {"n": 0, "hp": 0})
        d["n"] += 1
        d["hp"] += u.get("hp") or 0
    enemy_team = next((t for t in teams if t != my_team), None)
    mine = teams.get(my_team, {"n": 0, "hp": 0})
    enemy = teams.get(enemy_team, {"n": 0, "hp": 0})
    # létalité estimée CE TOUR = cibles ennemies distinctes avec un plan K! (killSure)
    lethal = {ev.get("targetId")
              for p in (res.get("attackPlans") or [])
              for ev in (p.get("evals") or []) if ev.get("killSure")}
    lethal_now = len(lethal)
    # score matériel [-1..+1] : 60% HP + 40% nombre d'unités
    tot_hp = (mine["hp"] + enemy["hp"]) or 1
    tot_n = (mine["n"] + enemy["n"]) or 1
    score = 0.6 * (mine["hp"] - enemy["hp"]) / tot_hp + 0.4 * (mine["n"] - enemy["n"]) / tot_n
    # flag à PRUDENCE ASYMÉTRIQUE
    if enemy["n"] == 0:
        flag = "won"
    elif mine["n"] == 0:
        flag = "lost"
    elif enemy["n"] - mine["n"] >= 2 and enemy["hp"] >= 1.8 * max(mine["hp"], 1):
        flag = "lost"   # nettement derrière → early-warning légitime (asymétrie)
    else:
        flag = "undecided"
    lean = "je mène" if score > 0.15 else ("je suis mené" if score < -0.15 else "serré")
    print(f"[verdict] decided={flag} · score={score:+.2f} ({lean}) · "
          f"léthal-ce-tour={lethal_now} cible(s) K!")
    print(f"  team{my_team} (MOI) : {mine['n']} units {mine['hp']} HP  |  "
          f"team{enemy_team} (ENN) : {enemy['n']} units {enemy['hp']} HP")
    print("  NB: 'won' uniquement à élimination adverse (prudence asymétrique vs la "
          "sur-estimation TF02) ; 'undecided' → juge par score/léthal, ne PAS abandonner.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "view", "act", "aiturn",
                                    "status", "dispose", "play", "guard",
                                    "rollout", "attach", "moves", "abilities",
                                    "reason", "verdict"])
    ap.add_argument("kind", nargs="?", default=None,
                    help="pour act: move|ability|finish|endturn")
    ap.add_argument("--spec", default=None,
                    help="play: JSON liste d'actions du tour")
    ap.add_argument("--end", action="store_true",
                    help="play: FIN DE TOUR explicite — applique le spec PUIS termine ton "
                         "tour même si des units pouvaient encore agir (réserve délibérée). "
                         "Sans --end, le tour se finit SEUL quand toutes tes units ont agi.")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--seed-bc", default=None,
                    help="build: chemin d'un seed BC CUSTOM (surcharge data/seed-bc.json). Sert a "
                         "valider un porteur HORS pool (ex. bloodTerminator/SavageEchoes) en injectant "
                         "son bloc Unit dans une copie du seed BC. N'ecrit jamais le seed BC partage.")
    ap.add_argument("--crit", default=None,
                    help="build: force CritChance,CritDamage sur les p-units (ex. '100,700'). "
                         "Restaure le crit que la normalisation strippe (crit héros = item I_Crit).")
    ap.add_argument("--crit-target", default=None, help="build: idem --crit pour les a-units")
    ap.add_argument("--block-target", default=None,
                    help="build: force BlockChance,BlockDamage sur les a-units (ex. '100,500')")
    ap.add_argument("--hp-target", type=int, default=None,
                    help="build: force Health+RemainingHealth des a-units (PV bas = kill déterministe)")
    ap.add_argument("--hp-player", type=int, default=None,
                    help="build: idem --hp-target mais pour les p-units (mover fragile côté joueur)")
    ap.add_argument("--dmg-target", type=int, default=None,
                    help="build: force le stat Damage des a-units (frappe adverse écrasante — "
                         "seul levier pour tuer une unité INVOQUÉE, dont les PV viennent du kit "
                         "du summoner et non du roster)")
    ap.add_argument("--roster", type=int, default=5,
                    help="taille de roster pour le tirage ALÉATOIRE "
                         "(ignoré si --p-units/--a-units fournis)")
    ap.add_argument("--p-units", default=None,
                    help="build: MON roster (team 1), ids séparés par virgule "
                         "(ex. 'custoVexilusPraetor,orksKillaKan,...'). "
                         "Sinon tirage aléatoire seedé.")
    ap.add_argument("--a-units", default=None,
                    help="build: roster ADVERSE (team 2), ids séparés par virgule")
    ap.add_argument("--p-mow", default=None,
                    help="build: MoW de MON équipe (1 id, ex. 'ultraDreadnought')")
    ap.add_argument("--a-mow", default=None,
                    help="build: MoW de l'équipe adverse (1 id)")
    ap.add_argument("--mow", action="store_true",
                    help="build: auto-pick 1 MoW aléatoire par équipe "
                         "(si ni --p-mow ni --a-mow)")
    ap.add_argument("--list-pool", action="store_true",
                    help="build: imprime le pool spawnable (units + MoW) et sort")
    ap.add_argument("--board", type=str, default=None,
                    help="build: swap le board du seed BC pour ce board dumpe (id, ex. C3_46). "
                         "Cherche data/boards/<pvp|syncPvp|global>/<id>.json ; le SPS apparie est "
                         "auto-applique (a la normalisation). Exclusif avec --board-pool. "
                         "Caracteristiques statiques (elevation/terrain/MoW) : cf. board.py.")
    ap.add_argument("--board-pool", type=str, default=None,
                    choices=["pvp", "syncPvp", "global"],
                    help="build: board ALEATOIRE (seede) depuis ce pool dumpe, filtre aux boards "
                         "avec assez de spawns/cote (+ MoW-capable si un MoW est en jeu). "
                         "Exclusif avec --board.")
    ap.add_argument("--advance", type=int, default=0)
    ap.add_argument("--maxpump", type=int, default=2000)
    ap.add_argument("--unit", type=int, default=None)
    ap.add_argument("--caster", type=int, default=None)
    ap.add_argument("--target", type=int, default=None)
    ap.add_argument("--ability", type=int, default=None)
    ap.add_argument("--to", default=None, help="col,row pour move")
    ap.add_argument("--auto", default=None,
                    choices=["hold", "gentle", "aggressive"],
                    help="guard: génère le spec de move automatiquement "
                         "(hold=rien, gentle=+~2 rangs, aggressive=max en avant) "
                         "au lieu de --spec — pour calibration/ranking objectif")
    ap.add_argument("--climb", action="store_true",
                    help="guard: hill-climb (retire le worst_unit, garde le meilleur "
                         "NET) au lieu d'un simple rapport")
    ap.add_argument("--cap", type=int, default=5,
                    help="guard --climb: budget TOTAL de sims (hold+base+variantes)")
    ap.add_argument("--plies", type=int, default=8,
                    help="rollout: cap de l'horizon adaptatif (demi-tours alternés)")
    ap.add_argument("--state-file", default=None,
                    help="fichier d'état alternatif (isolation multi-agent "
                         "parallèle) ; chemin relatif = ancré sur la racine "
                         "du repo, pas le cwd")
    ap.add_argument("--no-ai", dest="no_ai", action="store_true",
                    help="play: SELF-PLAY — joue MON tour, endturn (flip sur "
                         "l'adversaire), puis S'ARRÊTE SANS lancer le tour IA natif "
                         "(CheatRunAIMessage). C'est à l'AUTRE agent oracle de jouer "
                         "l'autre camp. cf. docs/rl/design.md §Self-play.")
    ap.add_argument("--from", dest="attach_from", default=None,
                    help="attach: state-file source (runner partagé) à copier")
    ap.add_argument("--team", type=int, default=None,
                    help="attach: camp de CE player (1|2 ; omis = auto-dérivé)")
    ap.add_argument("--runner", type=int, default=None,
                    help="attach: runnerId explicite (défaut = celui du --from)")
    a = ap.parse_args(argv)

    global STATE
    if a.state_file:
        sf = Path(a.state_file)
        # Chemin RELATIF ancre sur la RACINE du repo (pas le cwd) : le
        # state-file est l'enregistrement de PROPRIETE du runner (replace
        # scope au build + dispose) — resolu contre le cwd, un lancement
        # depuis scripts/python crashait _save_state (dossier data/ absent)
        # APRES initAndStart => runner fraichement built ORPHELIN qui mange
        # le cap MAX_RUNNERS. Meme chemin nominal = meme fichier, quel que
        # soit le cwd de l'acteur.
        STATE = sf if sf.is_absolute() else (ROOT / sf)

    sid = _resolve_session()
    _ensure_ai_trace(sid)
    dispatch = {"build": cmd_build, "view": cmd_view, "act": cmd_act,
                "aiturn": cmd_aiturn, "status": cmd_status,
                "dispose": cmd_dispose, "play": cmd_play, "guard": cmd_guard,
                "rollout": cmd_rollout, "attach": cmd_attach,
                "moves": cmd_moves, "abilities": cmd_abilities,
                "reason": cmd_reason, "verdict": cmd_verdict}
    return dispatch[a.cmd](sid, a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
