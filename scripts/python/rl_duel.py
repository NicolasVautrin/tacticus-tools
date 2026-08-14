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
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import (  # noqa: E402
    _resolve_session, _ensure_ai_trace, _load_seed_bc, _load_unspawnable,
    _normalize_and_extract_pool, _spawn_points_by_twpi,
    _patch_predefined_units, _patch_predefined_machines, _rpc,
    _load_board_dump, _load_board_pool,
    PLAYER_ID_HUMAN, PLAYER_ID_AI,
)
from rl_probe_step import _print_apply  # noqa: E402
import catalog_inject  # noqa: E402
import host_inputs  # noqa: E402
import oracle  # noqa: E402
import runner_state  # noqa: E402
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
STATE = ROOT / "logs" / "runners" / "duel_state.json"

# Identite de la session Frida courante (#379), posee UNE fois par `main()`. Le state-file
# en est ESTAMPE a l'ecriture et RECONFRONTE a la relecture : le fichier est prive au
# worktree, mais l'espace de `runnerId` est PARTAGE par tous les agents, et une (re)injection
# remet son compteur a 0 pendant que les fichiers survivent. Detail + tri-etat :
# `scripts/python/runner_state.py`.
SESSION: runner_state.SessionIdentity | None = None


def _save_state(d: dict) -> None:
    # Creer le repertoire : `logs/` est gitignore, donc ABSENT d'un checkout frais
    # (contrairement a l'ancien `data/`, qui existait toujours via la jonction).
    # Sans ce mkdir, un worktree d'agent echoue au premier build sur FileNotFoundError.
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(runner_state.stamp(d, SESSION)), encoding="utf-8")


def _read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_state(context: str = "rl_duel (pilotage)") -> dict:
    """Etat du duel, REFUSE s'il appartient a une autre session Frida (#379).

    `MATCH` passe en silence, `UNSTAMPED` passe en AVERTISSANT (state-file ecrit avant que
    cette garde existe -- un agent qui a build puis rebase mi-run est dans ce cas, et son
    runner est valide), `MISMATCH` / `UNSTAMPED_STALE` sortent en rc 2.
    """
    if not STATE.exists():
        print("[error] pas d'état de duel — lance `build` d'abord", file=sys.stderr)
        sys.exit(2)
    st = _read_state(STATE)
    if not runner_state.enforce(runner_state.verify(st, SESSION, STATE), context):
        sys.exit(2)
    return st


# --- helpers partagés (dédup : routines répétées sur plusieurs commandes) ---------
def _winner_team(w) -> int | None:
    """playerId natif (3=team1 / 4=team2 ; 0/None=aucun) -> n° d'équipe ou None."""
    return {3: 1, 4: 2}.get(w)


def _winner_label(w) -> str:
    """playerId natif -> libellé lisible ('team1'/'team2'/'no-winner'/'playerN')."""
    return {0: "no-winner", 3: "team1", 4: "team2"}.get(w, f"player{w}")


def _diag_porteur_ecarte(uid: str, seed_bc: dict, template_bc: dict) -> str:
    """Suffixe de diagnostic quand un montage TERTIAIRE echoue sur `uid` (#237-r1).

    `equip_relic` / `equip_mythic` ne connaissent QUE le BC qu'on leur passe : leur `KeyError` dit
    « absent de BC.Units -- injecter d'abord le porteur », ce qui est ACTIONNABLE quand le porteur
    manque au catalogue, et TROMPEUR quand il y est mais que `buildNormalizedBC` l'a ecarte (npc,
    unite non normalisable au rank demande) -- l'appelant vient alors de faire exactement ce que le
    message lui demande. Ces deux regimes se distinguent en confrontant les deux BC, la seule
    position d'ou on les voit tous les deux.

    Rend `""` hors de ces regimes : un diagnostic qui parle a tort est pire que pas de diagnostic.
    """
    au_seed = uid in {u.get("Id") for u in (seed_bc.get("Units") or [])}
    au_norm = uid in {u.get("Id") for u in (template_bc.get("Units") or [])}
    if au_seed and not au_norm:
        return (f"\n[diag] {uid!r} EST au catalogue du seed BC mais ABSENT du BC normalise : "
                f"buildNormalizedBC l'a ecarte (npc, ou non normalisable a ce rank). "
                f"Injecter le porteur ne changera rien -- verifier `--list-pool` et "
                f"data/unspawnable_rank<N>.json.")
    return ""


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


def _parse_place_specs(specs, label: str) -> list[tuple[str, int, int]]:
    """'unitId:col,row' -> (unitId, col, row). Leve ValueError sur forme invalide.

    Une entree = UNE occurrence de l'unite. Repeter l'option pour placer deux copies
    du meme id.

    ⚠ COUPE AU DERNIER `:`, pas au premier (#507) : un unitId de PALIER npc en porte deja un
    (`thousNpc2Screamer:45`, la forme qu'exige `--explicit-stats` et que `--p-units` doit
    reprendre VERBATIM, cf. la verification `uid not in p_units` du site d'appel). Avec un
    `partition`, `thousNpc2Screamer:45:3,0` donnait `uid='thousNpc2Screamer'` et
    `coords='45:3,0'` -> `col/row non entiers`, c'est-a-dire qu'AUCUN porteur npc a palier
    n'etait placable sur une tuile choisie. Le `rpartition` est sans effet sur la forme sans
    palier (`orksNob:3,1`), ou il n'y a qu'un seul `:`."""
    out: list[tuple[str, int, int]] = []
    for spec in (specs or []):
        uid, _, coords = str(spec).rpartition(":")
        uid = uid.strip()
        parts = [p.strip() for p in coords.split(",")]
        if not uid or len(parts) != 2:
            raise ValueError(f"{label}: forme attendue 'unitId:col,row', recu {spec!r}")
        try:
            col, row = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError(f"{label}: col/row non entiers dans {spec!r}") from None
        out.append((uid, col, row))
    return out


def _apply_place_overrides(units: list[dict], places: list[tuple[str, int, int]],
                           label: str) -> str | None:
    """Ecrase col/row des entrees `units` (forme initAndStart.playerUnits) dont
    l'`unitId` est cite. Une occurrence consommee par entree de `places` ; rend un
    message d'erreur si un id n'a pas assez d'occurrences."""
    used: dict[str, int] = {}
    for uid, col, row in places:
        idxs = [i for i, u in enumerate(units) if u["unitId"] == uid]
        k = used.get(uid, 0)
        if k >= len(idxs):
            return (f"{label}: '{uid}' place {k + 1} fois mais le roster n'en compte "
                    f"que {len(idxs)}")
        units[idxs[k]]["col"] = col
        units[idxs[k]]["row"] = row
        used[uid] = k + 1
    return None


def _board_playable(bc: dict) -> tuple[int, int, set[tuple[int, int]]]:
    """(width, height, tuiles INJOUABLES) de `BC.Board`.

    `Board.Tiles` est indexe [col].Tile[row] (mesure : board 7x9 -> 7 entrees de 9).
    `ForceUnplayable` est le seul drapeau de la config qui retire une tuile du plateau ;
    le refus natif, lui, vit dans
    `IdunBattle.Operations.AddUnitOperation$$AreTilesDisallowedAndLog` (tuile non
    marchable OU `TileContentComponent$$IsFilled`)."""
    board = bc.get("Board") or {}
    w, h = int(board.get("Width") or 0), int(board.get("Height") or 0)
    bad: set[tuple[int, int]] = set()
    for c, colentry in enumerate(board.get("Tiles") or []):
        for r, t in enumerate((colentry or {}).get("Tile") or []):
            if (t or {}).get("ForceUnplayable"):
                bad.add((c, r))
    return w, h, bad


def _validate_placements(bc: dict, player_units: list[dict],
                         placed: list[tuple[str, int, int, int]]) -> list[str]:
    """Refuse AVANT le build une tuile hors board, injouable, ou reclamee deux fois.

    POURQUOI EN AMONT, alors que `_verify_placements` confronte deja APRES : les quatre
    gardes natives de `IdunBattle.Operations.AddUnitOperation$$Execute` rendent NUL EN
    SILENCE, donc un refus se lit comme un succes tant qu'on n'a pas releve l'etat -- et
    entre-temps le runner est construit, enregistre, et mange le cap partage. Une tuile
    hors board ne produit meme pas de tuile a examiner. Ici on tranche ce qui est
    decidable sur la CONFIG seule ; `_verify_placements` garde ce qui ne l'est pas
    (fog, reservation, draft en attente, contenu de tuile a l'instant du spawn)."""
    w, h, unplayable = _board_playable(bc)
    problems: list[str] = []
    if w <= 0 or h <= 0:
        return ["board sans Width/Height exploitables -- placement invalidable"]
    for uid, col, row, team in placed:
        if not (0 <= col < w and 0 <= row < h):
            problems.append(f"{uid} (team{team}) @({col},{row}) HORS BOARD "
                            f"(board {w}x{h}, col 0..{w - 1} / row 0..{h - 1})")
        elif (col, row) in unplayable:
            problems.append(f"{uid} (team{team}) @({col},{row}) tuile INJOUABLE "
                            f"(Board.Tiles[{col}].Tile[{row}].ForceUnplayable)")
    # Collision : deux unites sur la MEME tuile. On confronte l'ensemble COMPLET des
    # positions de deploiement (spawns retenus + tuiles forcees), pas seulement les
    # tuiles forcees : poser une unite sur un spawn deja attribue a une autre est
    # exactement le cas que `AreTilesDisallowedAndLog` refuse (`IsFilled`).
    occ: dict[tuple[int, int], list[str]] = {}
    for u in player_units:
        occ.setdefault((int(u["col"]), int(u["row"])), []).append(str(u["unitId"]))
    for tile, ids in sorted(occ.items()):
        if len(ids) > 1:
            problems.append(f"tuile ({tile[0]},{tile[1]}) reclamee par {len(ids)} unites: "
                            f"{ids} -- le natif n'en deploiera qu'une")
    return problems


def _base_unit_id(uid: str) -> str:
    """`thousNpc2Screamer:45` -> `thousNpc2Screamer`. Le suffixe de PALIER n'est pas republie.

    Meme coupe qu'au `rpartition` de `_parse_place_specs` (#507), mais CONDITIONNELLE : on ne
    tronque que si la partie droite est un ENTIER. Un `unitId` qui porterait un `:` non numerique
    resterait entier, ce qui est le sens prudent -- au pire la confrontation compare deux noms
    identiques."""
    head, sep, tail = str(uid).rpartition(":")
    return head if (sep and head and tail.strip().isdigit()) else str(uid)


def _published_unit_ids(uid: str) -> tuple[str, ...]:
    """Les cles sous lesquelles le jeu PUBLIE l'unite `uid` dans `decisionView.units[].visualId`,
    de la PLUS SPECIFIQUE a la plus generale (#895).

    `--p-units`/`--a-units`/`--place` nomment un **unitId de CONFIG** ; `decisionView` publie un
    **visualId**. Pour les 254 unites `lineup` les deux coincident, et les deux gardes ci-dessous
    comparaient donc les bonnes chaines... jusqu'a ce qu'un porteur NPC arrive. MESURE (#895,
    gameconfig du build `rnca9r7q6c`) : **429 unites sur 683** ont `visualId != id`, TOUTES `npc`
    ou `summons` -- `tauBossRiptide` -> `GuildBoss11Boss1TauRiptide`,
    `admecBossBelisarius` -> `GuildBoss10Boss1AdmecBelisarius`, `adeptBossCanoness` ->
    `adeptCanoness`... Le garde de roster rendait donc `demande x1 mais MONTE x0` -- un refus DUR
    (rc 3) -- pour un boss qui EST en bataille, ce qui se lit comme « ce porteur n'est pas
    montable » alors qu'il l'est. C'est le seul canal par lequel un lot d'abilities de boss
    arrivait « non confrontable ».

    L'ORDRE compte, et le repli est CONDITIONNEL au site d'appel (`X or Y`, jamais un `max`) :
    l'id EXACT reste primaire, le `visualId` de config n'est consulte QUE si l'exact ne trouve
    RIEN. Aucune detection existante ne peut donc disparaitre -- on ne retire que le faux positif.
    ⚠ La resolution est MANY-TO-ONE (`adeptBossCanoness` et `adeptBossCanonessLHE` publient tous
    deux `adeptCanoness`) : deux npc distincts qui partagent un visualId sont indiscernables par
    ce canal. C'est deja mieux que le zero franc d'aujourd'hui, mais ca ne les separe pas.
    Gameconfig illisible -> on rend l'id de base seul (comportement d'avant, jamais une exception).
    """
    base = _base_unit_id(uid)
    try:
        import gameconfig as _GC
        vis = (_GC.unit(base) or {}).get("visualId")
    except Exception:                                     # gameconfig absent -> pas de repli
        vis = None
    return (base,) if (not vis or str(vis) == base) else (base, str(vis))


def _verify_roster(dec: dict, p_units: list[str], a_units: list[str]) -> list[str]:
    """Confronte le ROSTER DEMANDE au roster REELLEMENT MONTE, camp par camp (#287-r13).

    POURQUOI, alors que `_verify_placements` confronte deja : ce garde-la ne visite QUE les unites
    citees par `--place`/`--a-place`. Une unite du roster confiee au placement NATIF
    (`BC.PredefinedUnits` -> `IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits`) qui
    n'arrive pas ne traverse AUCUNE de ses lignes. MESURE (#287-r13, board `C1_02`, seed 4242) :
    `--a-units necroWarden x4` avec TROIS `--a-place` monte **3 unites sur 4**, et `build` rend
    `[build] placements verifies OK (4)` puis **rc = 0** -- il IMPRIME meme le roster adverse a
    quatre entrees. La geometrie mesuree n'est alors pas celle demandee, et un cote de bascule
    disparait sans trace (c'est ainsi qu'un bras du predicat de `1200` a manque au premier jet de
    `probe_287r11`).

    ⚠ LE DEFICIT SEUL FAIT FAUTE. Un SURPLUS (summon pose au deploiement, unite de boss) est
    NORMAL : il est imprime et jamais bloquant. Les MACHINES OF WAR sont hors perimetre -- elles
    vivent dans `decisionView.mows`, et leur propre panne muette a deja son avertissement
    (`_board_mow_ok`).

    Rend la liste des ecarts (DEFICITS seuls)."""
    have: dict[tuple[str, int], int] = {}
    for u in (dec.get("units") or []):
        key = (_base_unit_id(u.get("visualId")), int(u.get("team") or 0))
        have[key] = have.get(key, 0) + 1
    problems: list[str] = []
    for team, roster in ((1, p_units), (2, a_units)):
        want: dict[str, int] = {}
        for uid in roster:
            b = _base_unit_id(uid)
            want[b] = want.get(b, 0) + 1
        for uid, n in sorted(want.items()):
            # #895 : l'id EXACT d'abord, le `visualId` de config en REPLI seulement s'il rend 0
            # (cf. `_published_unit_ids`) -- 429 npc/summons sur 683 publient un autre nom.
            got = 0
            for key in _published_unit_ids(uid):
                got = have.get((key, team), 0)
                if got:
                    break
            if got < n:
                problems.append(f"{uid} (team{team}) demande x{n} mais MONTE x{got} "
                                f"-- {n - got} exemplaire(s) absent(s) du deploiement")
    return problems


def _verify_placements(sid: int, rid: int, wanted: list[dict], dec: dict | None = None) -> list[str]:
    """Confronte les placements DEMANDES aux positions REELLEMENT obtenues.

    Raison d'etre : `IdunBattle.Operations.AddUnitOperation$$Execute` abandonne en
    RETOUR NUL SILENCIEUX sur QUATRE gardes -- `AreTilesDisallowedAndLog` (tuile non
    marchable ou `TileContentComponent$$IsFilled`, la seule qui LOG),
    `TilesAreReserved`, `TilesArePendingDrafting`, `TilesAreInFog` -- ni exception, ni
    event d'erreur cote appelant. Un placement refuse se lirait donc comme un succes.
    Rend la liste des ecarts."""
    res = dec if dec is not None else _decision(sid, rid)
    units = res.get("units") or []
    # Cle = (visualId, team) : le MEME unitId peut etre des DEUX cotes (rosters croises),
    # et sans la team un placement joueur refuse se lirait comme honore par l'unite ADVERSE
    # homonyme -- faute constatee au premier jet de ce garde.
    pos_by: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for u in units:
        p = u.get("pos") or {}
        if p.get("col") is None:
            continue
        pos_by.setdefault((str(u.get("visualId")), int(u.get("team") or 0)), []).append(
            (int(p["col"]), int(p["row"])))
    problems: list[str] = []
    for w in wanted:
        # #895 : MEME resolution que `_verify_roster` -- l'id EXACT d'abord (comportement
        # historique intact), puis le suffixe de PALIER retire, puis le `visualId` de config.
        # Sans elle, tout `--place` d'un porteur NPC (429/683) ou a palier (`tauBossRiptide:4`)
        # rapportait « present NULLE PART (non deploye) » pour une unite CORRECTEMENT posee.
        got = pos_by.get((w["unitId"], w["team"]), [])
        if not got:
            for key in _published_unit_ids(w["unitId"]):
                got = pos_by.get((key, w["team"]), [])
                if got:
                    break
        if (w["col"], w["row"]) not in got:
            problems.append(f"{w['unitId']} (team{w['team']}) demande @({w['col']},{w['row']}) "
                            f"mais present @{got or 'NULLE PART (non deploye)'}")
    return problems


# --- #477-r6 : BC.UnitModifiers, le point d'entree NATIF de modification de stats -----
#
# `BattleConfiguration.UnitModifiers` (champ @0x50, `Dictionary<string,
# List<IdunBattleLogic.Shared.UnitModifier>>`, cle = unitId SANS suffixe de rarete) est lu
# par `IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits` (et
# `...$$AddBossUnit`) juste apres la creation de l'entite, puis dispatche par
# `...$$ApplyModifiers`. C'est le pendant PROPRE de `--unit-stat` : il produit de VRAIS
# `StatModifier` pousses par une Operation, la ou `--unit-stat` reecrit un scalaire du
# template `BC.Units[]`.
#
# CHAMPS de `UnitModifier` (disposition MESUREE en live, RPC `classFields`, build
# `rnca9r7q6c`) : `ModificationType`@0x10 (enum `UnitModificationType` :
# 0=Stat, 1=AbilityVariable, 2=AbilityConstant, 3=InitialSpawnAmountDecrease),
# `Id`@0x18 (string), `SubId`@0x20 (string), `IsBuff`@0x28, `IsPercentage`@0x29,
# `Amount`@0x2c (Int32).
# ⚠ `IsBuff` et `IsPercentage` ne sont JAMAIS LUS par `ApplyModifiers` : la nature
# (pourcentage vs absolu) est cablee PAR `Id` dans le natif, pas portee par le modifier.
#
# Les HUIT `Id` acceptes -- litteraux du binaire, chacun CONFRONTE en live (temoin vs
# modifie, memes positions ; voir probe_477r6_unit_modifiers.py). Tout autre `Id` tombe
# dans la branche de log de `ApplyModifiers` et n'applique RIEN : c'est le mode de panne
# silencieux principal, d'ou le refus explicite ci-dessous.
#
# | Id           | methode native            | stat combatSnapshot | Amount        |
# |--------------|---------------------------|---------------------|---------------|
# | dmg          | ModifyUnitAttack          | attack              | POURCENTAGE   |
# | fixedArmor   | ModifyUnitFixedArmor      | fixedArmor          | POURCENTAGE   |
# | movement     | ModifyUnitMovement        | movement            | ABSOLU        |
# | hits         | ModifyUnitHits            | extraHits           | ABSOLU        |
# | hp           | ModifyUnitHp              | health              | POURCENTAGE   |
# | blockChance  | ModifyUnitBlockChance     | blockChance         | ABSOLU        |
# | critDmg      | ModifyUnitCritDamage      | critDamage          | POURCENTAGE   |
# | critChance   | ModifyUnitCritChance      | critChance          | ABSOLU        |
#
# POURCENTAGE passe par `IdunBattle.Operations.SetupGameOperation$$CalculatePercentage`
# (Fix64, arrondi puis `Ceiling`) et la valeur finale vaut `base - pourcentage(base)` ;
# ABSOLU vaut `StatComponent.CurrentValue - Amount`. Mesures (board MC1_67, rank 17) :
# `dmg` 10 sur attack 2609 -> 2348 ; `movement` 1 sur 4 -> 3 ; `hits` 1 sur 0 -> -1 ;
# `blockChance` 10 sur 50 -> 40 ; `critChance` 10 sur 50 -> 40 ; `critDmg` 100 sur
# 300 -> 0.
# ⚠ SEUL `fixedArmor` a une base NATIVE differente de la valeur affichee : le natif lit
# un champ du COMPOSANT (`+0x48`) que `combatSnapshot` n'expose pas. Mesure : affiche
# 3806, base native 2609 -- `statModSources` rend le `StatModifier` pose, `total = -2349`
# pour `Amount = 90`, soit exactement `-ceil(2609 x 90%)`. Ne PAS predire cette valeur
# depuis l'affichage.
# Ce que le levier apporte face a `--unit-stat`, MESURE : sur la meme unite, le temoin
# n'a AUCUN mod `fixedArmor` dans `statModSources`, le bras `--unit-modifier` en a un --
# c'est un vrai `StatModifier` pose par une Operation, pas un scalaire ecrase.
UNIT_MODIFIER_STATS: dict[str, str] = {
    "dmg": "attack",
    "fixedArmor": "fixedArmor",
    "movement": "movement",
    "hits": "extraHits",
    "hp": "health",
    "blockChance": "blockChance",
    "critDmg": "critDamage",
    "critChance": "critChance",
}


def _split_hors_json(s: str, sep: str) -> list[str]:
    """Decoupe `s` sur `sep`, mais JAMAIS a l'interieur d'une valeur JSON composee.

    Foyer du decoupage de `--unit-stat` ("VisualId:Champ=Valeur[,Champ=Valeur][;VisualId:...]").
    Le `str.split` naif d'avant coupait `Traits=["Summon","Decoy"]` en `'["Summon"'` + `'"Decoy"]'`
    et le premier morceau rendait `valeur non-JSON` -- ce qui rendait INJOUABLE tout montage a
    valeur-liste de plus d'un element (mesure #419-r7, sur le bras UNION de
    `#589-r1-r1-r2-r1-r2`, ecrit et decrit comme confrontable).

    On suit la PROFONDEUR (`[]`/`{}`) et l'etat CHAINE (`"` avec echappement `\\`) : un separateur
    n'est un separateur qu'a profondeur 0, hors chaine. Aucune autre forme n'est reconnue --
    ce n'est pas un parseur JSON, c'est le decoupeur qui lui livre ses morceaux, et un JSON mal
    forme reste rejete PLUS LOIN par `json.loads`, avec son message.
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str = False
    esc = False
    for ch in str(s):
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth <= 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def _parse_unit_modifier_specs(specs) -> list[tuple[str, str, int]]:
    """'unitId:Id:Amount' -> (unitId, Id, Amount). Leve ValueError sur forme invalide
    ou sur un `Id` hors des huit que `ApplyModifiers` sait dispatcher."""
    out: list[tuple[str, str, int]] = []
    for spec in (specs or []):
        parts = [p.strip() for p in str(spec).split(":")]
        if len(parts) != 3 or not all(parts[:2]):
            raise ValueError(
                f"--unit-modifier: forme attendue 'unitId:Id:Amount', recu {spec!r}")
        uid, ident, amount_s = parts
        if ident not in UNIT_MODIFIER_STATS:
            raise ValueError(
                f"--unit-modifier: Id '{ident}' inconnu du natif -- "
                f"IdunBattle.Operations.SetupGameOperation$$ApplyModifiers ne dispatche "
                f"que {sorted(UNIT_MODIFIER_STATS)} ; tout autre Id part dans sa branche "
                f"de log et n'applique RIEN (panne SILENCIEUSE)")
        try:
            amount = int(amount_s)
        except ValueError:
            raise ValueError(
                f"--unit-modifier: Amount non entier dans {spec!r}") from None
        out.append((uid, ident, amount))
    return out


def _apply_unit_modifiers(bc: dict, mods: list[tuple[str, str, int]]) -> None:
    """Ecrit `BC.UnitModifiers`. A appeler APRES la normalisation (`buildNormalizedBC`
    ne touche qu'a `Units`/`Board`/`SpawnPointSetIndex`, donc aucun etage ne le reecrit
    -- contrairement au piege `TertiaryAbilityLevel` de #237)."""
    table: dict[str, list[dict]] = dict(bc.get("UnitModifiers") or {})
    for uid, ident, amount in mods:
        table.setdefault(uid, []).append({
            "ModificationType": "Stat",
            "Id": ident,
            "SubId": None,
            "IsBuff": False,
            "IsPercentage": False,
            "Amount": amount,
        })
    bc["UnitModifiers"] = table


def _verify_unit_modifiers(sid: int, rid: int,
                           mods: list[tuple[str, str, int]]) -> list[str]:
    """Releve en bataille la stat visee par chaque modifier, et rougit sur le SEUL cas
    dont l'attendu se calcule sans temoin : `hp` avec `Amount > 99` DOIT retirer l'unite
    du deploiement (`...$$IsPredefinedUnitDisabledByModifiers` -> `Id == "hp" &&
    Amount > 99`). Pour les autres, la valeur relevee est IMPRIMEE (l'attendu exige un
    bras temoin -- c'est le role de probe_477r6_unit_modifiers.py, pas du build)."""
    snap = (_rpc(sid, "combatSnapshot", [{"runnerId": rid}], timeout=30)
            .get("result") or {})
    obs = (_rpc(sid, "observeBattle", [{"runnerId": rid}], timeout=30)
           .get("result") or {})
    vis: dict[int, str] = {}
    for u in (obs.get("units") or []):
        vis[int(u["entityId"])] = str(u["visualId"])
        vis[int(u["squadId"])] = str(u["visualId"])
    stats_by: dict[str, dict] = {}
    for u in (snap.get("units") or []):
        name = vis.get(int(u.get("entityId") or -1))
        if name:
            stats_by[name] = u.get("stats") or {}
    problems: list[str] = []
    for uid, ident, amount in mods:
        key = UNIT_MODIFIER_STATS[ident]
        if ident == "hp" and amount > 99:
            if uid in stats_by:
                problems.append(
                    f"{uid}: hp={amount} (>99) devait EMPECHER le deploiement "
                    f"(IsPredefinedUnitDisabledByModifiers) -- l'unite est pourtant la")
            else:
                print(f"[build] unit-modifier {uid}:hp:{amount} -> unite NON deployee "
                      f"(attendu : Amount > 99)")
            continue
        if uid not in stats_by:
            problems.append(f"{uid}: absent de la bataille -- le modifier ne peut pas "
                            f"avoir mordu (unite hors --a-units, ou non deployee)")
            continue
        print(f"[build] unit-modifier {uid}:{ident}:{amount} -> {key}="
              f"{stats_by[uid].get(key)}")
    return problems


def _equip_items_choisi(a):
    """Tri-etat de l'equipement d'items (#419-r6) : `True` / `False` / `None` = le defaut.

    Depuis #419-r6 le defaut est « EQUIPER » (`_EQUIP_ITEMS_PAR_DEFAUT`), donc le drapeau
    UTILE est le NEGATIF : `--no-bis-items` restitue le regime d'avant #419-r5, ou
    `CritChance`/`CritDamage`/`BlockChance`/`BlockDamage` valent 0 sur toute unite et ou le
    crit est structurellement impossible. `--bis-items` reste accepte (il demandait deja ce
    qui est desormais le defaut) : c'est un no-op explicite, pas une erreur.

    Rendre `None` quand aucun des deux n'est pose est ce qui laisse `TACTICUS_BIS_ITEMS`
    trancher -- un `False` en dur ici ecraserait la bascule d'environnement en silence.
    """
    if getattr(a, "no_bis_items", False):
        return False
    if getattr(a, "bis_items", False):
        return True
    return None


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
    # --equip-relic (#237) : ETAT 2 de la gate de confrontabilite (« porteur au pool, relique NON
    # equipee »). Les TROIS ecritures sont faites par `catalog_inject.equip_relic`, APRES la
    # normalisation -- et c'est le seul ordre correct :
    #   * `buildNormalizedBC` ECRASE `TertiaryAbilityLevel` a `targetAbilityLevel` (50) des que
    #     `TertiaryAbility` est non nul (`normalize-bc/json-build.ts`). Poser AVANT reviendrait
    #     donc a jouer 50, que le natif clampe au dernier palier -- jamais le niveau demande ;
    #   * `BC.Abilities` traverse `buildNormalizedBC` INTACT (le RPC ne touche que `Units`,
    #     `Board` et `SpawnPointSetIndex`), donc la config d'ability se pose aussi bien apres.
    relic_specs = []
    for spec in (getattr(a, "equip_relic", None) or []):
        try:
            relic_specs.append(catalog_inject.parse_relic_spec(spec))
        except ValueError as e:
            print(f"[error] --equip-relic: {e}", file=sys.stderr)
            return 2
    # --equip-mythic (#999) : la mythique d'une Machine of War. MEME voie tertiaire que la relique
    # cote bataille (`UnitFactory$$AddConfiguredAbilities` n'en a qu'UNE), donc meme ordre --
    # `catalog_inject.equip_mythic` APRES la normalisation. UNE difference de montage, et elle est
    # structurelle : plusieurs MoW porteuses sont HORS du pool du seed BC, donc on injecte le
    # porteur au catalogue AVANT la normalisation, sans quoi `equip_mythic` leve `KeyError`.
    mythic_specs = []
    for spec in (getattr(a, "equip_mythic", None) or []):
        try:
            mythic_specs.append(catalog_inject.parse_mythic_spec(spec))
        except ValueError as e:
            print(f"[error] --equip-mythic: {e}", file=sys.stderr)
            return 2
    # --explicit-stats (#419-r1-tr12-r2) : porteurs NPC / SUMMON. La formule heros
    # `IStatsFormula.StatsUsingProgressionIndexFor` LEVE sur eux (pas de table de progression de
    # heros) -> `skipped`, jamais au pool. On injecte l'entree si elle manque, puis on calcule les
    # stats par le chemin natif de leur propre categorie (`catalog_inject.explicit_stats`, mirror de
    # `UnitProgression$$GetNpcStats` / `$$GetSummonStats`) et on les passe au RPC, qui les ECRIT au
    # lieu d'appeler la formule.
    explicit_specs = list(getattr(a, "explicit_stats", None) or [])
    explicit_patch: dict = {}
    if explicit_specs:
        missing = [u for u in explicit_specs
                   if u not in {x.get("Id") for x in (seed_bc.get("Units") or [])}]
        if missing:
            try:
                seed_bc, added, added_ab, unresolved = catalog_inject.augment(
                    seed_bc, missing, rank=a.rank)
            except KeyError as e:
                print(f"[error] --explicit-stats: {e}", file=sys.stderr)
                return 2
            print(f"[explicit-stats] catalogue: +{len(added)} unites {added} "
                  f"+{len(added_ab)} configs d'ability"
                  + (f" | sans config (marqueurs): {unresolved}" if unresolved else ""))
        for uid in explicit_specs:
            try:
                rep = catalog_inject.explicit_stats(uid)
            except (KeyError, ValueError) as e:
                print(f"[error] --explicit-stats {uid}: {e}", file=sys.stderr)
                return 2
            explicit_patch[uid] = rep["fields"]
            src = rep["source"]
            extra = f" via {rep['ability']}" if rep.get("ability") else ""
            print(f"[explicit-stats] {uid} <- {src}{extra} : "
                  f"hp={rep['fields'].get('Health')} dmg={rep['fields'].get('Damage')} "
                  f"fixedArmor={rep['fields'].get('FixedArmor')}"
                  + ("   [MONTAGE: le jeu ecrit 0 au catalogue pour un summon,"
                     " ces valeurs sont celles du SPAWN]" if src == "summon-spawn" else ""))
    # --equip-relic : injection catalogue du porteur AVANT la normalisation (#237-r1). PENDANT
    # EXACT du bloc `--equip-mythic` ci-dessous, et pour la meme raison structurelle : `equip_relic`
    # court APRES `_normalize_and_extract_pool` (le niveau EXACT l'exige, cf. bloc en tete de
    # `cmd_build`), donc un porteur absent du seed BC n'est PAS dans le BC normalise et la commande
    # sortait en `rc 2`. Mesure du gisement (2026-08-15, gameconfig de `t6dpr4k06g`) : sur les 32
    # abilities de relique, **5** n'ont AUCUN porteur au seed BC (`BladeOfTheAncestors`/`votanUthar`,
    # `DawnBlade`/`tauFarsight`, `TheArdentBlade`/`adeptCelestine`, `VolummsMasterArtifice`/
    # `votanIronmaster`, `WyrdmakersHelm`/`spaceWolfPriest`) et **9 porteurs sur 65** sont hors seed
    # -- c'est l'ETAT 3 de la gate de confrontabilite, qui exigeait deux commandes sans que rien ne
    # le dise. Aucun effet quand le porteur est deja la (l'immense majorite : etats 1 et 2).
    if relic_specs:
        have = {x.get("Id") for x in (seed_bc.get("Units") or [])}
        missing_r = sorted({u for u, _a, _l in relic_specs if u not in have})
        if missing_r:
            try:
                seed_bc, added, added_ab, unresolved = catalog_inject.augment(
                    seed_bc, missing_r, rank=a.rank)
            except KeyError as e:
                print(f"[error] --equip-relic: {e}", file=sys.stderr)
                return 2
            print(f"[relic] catalogue: +{len(added)} unites {added} "
                  f"+{len(added_ab)} configs d'ability"
                  + (f" | sans config (marqueurs): {unresolved}" if unresolved else ""))
    # --equip-mythic : injection catalogue du porteur AVANT la normalisation (cf. bloc plus haut).
    if mythic_specs:
        have = {x.get("Id") for x in (seed_bc.get("Units") or [])}
        missing_m = sorted({u for u, _a, _l in mythic_specs if u not in have})
        if missing_m:
            try:
                seed_bc, added, added_ab, unresolved = catalog_inject.augment(
                    seed_bc, missing_m, rank=a.rank)
            except KeyError as e:
                print(f"[error] --equip-mythic: {e}", file=sys.stderr)
                return 2
            print(f"[mythic] catalogue: +{len(added)} unites {added} "
                  f"+{len(added_ab)} configs d'ability"
                  + (f" | sans config (marqueurs): {unresolved}" if unresolved else ""))
    # --board fixe : swap au moment de la normalisation (buildNormalizedBC boardJson+spawnPointSetIndex).
    template_bc, pool, pool_mow = _normalize_and_extract_pool(
        sid, seed_bc, a.rank, board_dump=fixed_board_dump,
        explicit_stats=explicit_patch or None,
        equip_items=_equip_items_choisi(a))
    for uid, ability, lvl in relic_specs:
        try:
            rep = catalog_inject.equip_relic(
                template_bc, uid, ability, lvl,
                allow_unlisted=bool(getattr(a, "allow_unlisted_relic", False)))
        except (ValueError, KeyError) as e:
            print(f"[error] --equip-relic {uid}:{ability}:{lvl} -> {e}"
                  f"{_diag_porteur_ecarte(uid, seed_bc, template_bc)}", file=sys.stderr)
            return 2
        clamp = (f"  [clamp] {lvl} > {rep['levelsAvailable']} paliers -> dernier"
                 if rep["clamped"] else "")
        print(f"[relic] {uid} <- {ability} (TriggeredAbilityType={rep['abilityId']}) "
              f"TertiaryAbilityLevel={lvl} "
              f"config{'+' if rep['configAdded'] else '='}BC{clamp}")
    for uid, ability, lvl in mythic_specs:
        try:
            rep = catalog_inject.equip_mythic(
                template_bc, uid, ability, lvl,
                allow_unlisted=bool(getattr(a, "allow_unlisted_mythic", False)))
        except (ValueError, KeyError) as e:
            print(f"[error] --equip-mythic {uid}:{ability}:{lvl} -> {e}"
                  f"{_diag_porteur_ecarte(uid, seed_bc, template_bc)}", file=sys.stderr)
            return 2
        clamp = (f"  [clamp] {lvl} > {rep['levelsAvailable']} paliers -> dernier"
                 if rep["clamped"] else "")
        print(f"[mythic] {uid} <- {ability} (TriggeredAbilityType={rep['abilityId']}) "
              f"TertiaryAbilityLevel={lvl} "
              f"config{'+' if rep['configAdded'] else '='}BC{clamp}")
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

    # --place / --a-place (#477-r5) : placement sur TUILE EXACTE via AddUnitMessage.
    # Cote adverse, l'unite quitte BC.PredefinedUnits (que le natif place lui-meme sur le
    # SpawnPointGroup, cf. `IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits`)
    # pour rejoindre les `playerUnits` d'`initAndStart` avec playerId=PLAYER_ID_AI.
    try:
        p_places = _parse_place_specs(getattr(a, "place", None), "--place")
        a_places = _parse_place_specs(getattr(a, "a_place", None), "--a-place")
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    for uid, _c, _r in p_places:
        if uid not in p_units:
            print(f"[error] --place: '{uid}' n'est pas dans --p-units {p_units}",
                  file=sys.stderr)
            return 2
    for uid, _c, _r in a_places:
        if uid not in a_units:
            print(f"[error] --a-place: '{uid}' n'est pas dans --a-units {a_units}",
                  file=sys.stderr)
            return 2
    # a_predef = ce qui reste confie au placement natif ; a_hand = pose a la main.
    a_predef = list(a_units)
    a_hand: list[tuple[str, int, int]] = []
    for uid, col, row in a_places:
        if uid not in a_predef:
            print(f"[error] --a-place: '{uid}' place plus de fois qu'il n'apparait "
                  f"dans --a-units", file=sys.stderr)
            return 2
        a_predef.remove(uid)
        a_hand.append((uid, col, row))

    # --unit-modifier (#477-r6) : BC.UnitModifiers, lu par
    # `IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits`. Deux refus AMONT,
    # parce que les deux pannes correspondantes sont SILENCIEUSES cote natif : un `Id`
    # hors des huit part dans la branche de log de `ApplyModifiers` (levee par le parse),
    # et une unite hors `BC.PredefinedUnits` n'est jamais confrontee au dictionnaire --
    # `AddPredefinedUnits` est le SEUL chemin qui le lit pour une unite reguliere, donc
    # une p-unit (posee par `AddUnitMessage`) ou une cible de `--a-place` (sortie des
    # PredefinedUnits, cf. plus haut) ne recevrait RIEN.
    try:
        unit_mods = _parse_unit_modifier_specs(getattr(a, "unit_modifier", None))
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    for uid, ident, _amt in unit_mods:
        if uid not in a_predef:
            hint = ("il est pose a la main par --a-place, donc SORTI de "
                    "BC.PredefinedUnits" if uid in {u for u, _c, _r in a_places}
                    else f"roster adverse confie au natif = {a_predef}")
            print(f"[error] --unit-modifier: '{uid}' ({ident}) n'est pas une unite "
                  f"PREDEFINIE de l'equipe adverse -- {hint}. BC.UnitModifiers n'est lu "
                  f"que par SetupGameOperation$$AddPredefinedUnits (et $$AddBossUnit) : "
                  f"pour une unite du joueur, utiliser --unit-stat.", file=sys.stderr)
            return 2

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
    _patch_predefined_units(bc, a_predef)
    _patch_predefined_machines(bc, p_mow, a_mow)
    if unit_mods:
        _apply_unit_modifiers(bc, unit_mods)
        for uid, ident, amount in unit_mods:
            print(f"[build] --unit-modifier {uid}:{ident}:{amount} "
                  f"(-> {UNIT_MODIFIER_STATS[ident]})")

    # --crit/--block "CC,CD" : restaure des stats de combat sur les TEMPLATES Units des
    # p-units (la normalisation les remet à 0 ; AddUnit honore le template, cf. probe). Sert
    # à tester crit/block en combat — le crit d'un héros vient des items I_Crit (cf. itemSlots),
    # absent d'un build frais. --crit-target applique aussi à l'adversaire.
    def _patch_combat_stat(visual_ids: set[str], field_c: str, field_d: str, spec: str):
        cc, cd = (int(x) for x in spec.split(","))
        for u in bc.get("Units", []):
            if u.get("VisualId") in visual_ids:
                u[field_c] = cc; u[field_d] = cd
    def _visual_set(unit_ids) -> set[str]:
        """Les `VisualId` que ces `unitId` designent dans `BC.Units`.

        ⚠ **UN PORTEUR `--explicit-stats` N'A PAS LE MEME `Id` QUE SON `VisualId`**, et sans cette
        reduction TOUS les leviers de combat ci-dessous sont SILENCIEUSEMENT INERTES sur lui.
        Mesure (#1073) : `catalog_inject.augment(bc, ['darkaNpc3Terminator:45'])` ecrit
        `Id='darkaNpc3Terminator:45'` et `VisualId='darkaNpc3Terminator'` -- le suffixe `:<palier>`
        selectionne la ligne de `units.npc[].stats[]`, il ne fait pas partie de l'identite visuelle.
        La comparaison `u['VisualId'] in {'darkaNpc3Terminator:45'}` ne pouvait donc jamais tenir :
        `--block-player 100,50` ne posait AUCUN blocage, et le bras de probe qui en depend rendait
        `indisponible` pour une cause qui n'avait rien a voir avec la mecanique mesuree.

        La reduction coupe au DERNIER `:` (meme regle que `_parse_place_specs`, #507) et est un
        SUR-ENSEMBLE : l'id nu reste dans le set, donc aucun appelant existant ne change de
        comportement."""
        out: set[str] = set()
        for uid in (unit_ids or []):
            out.add(uid)
            court, sep, _pal = str(uid).rpartition(":")
            if sep and court:
                out.add(court)
        return out

    p_set, a_set = _visual_set(p_units), _visual_set(a_units)
    if getattr(a, "crit", None):
        _patch_combat_stat(p_set, "CritChance", "CritDamage", a.crit)
    if getattr(a, "crit_target", None):
        _patch_combat_stat(a_set, "CritChance", "CritDamage", a.crit_target)
    if getattr(a, "block_target", None):
        _patch_combat_stat(a_set, "BlockChance", "BlockDamage", a.block_target)
    if getattr(a, "block_player", None):
        # Pendant côté JOUEUR de --block-target (comme --hp-player l'est de --hp-target). Un héros
        # frais a BlockChance/BlockDamage = 0 (le block vient des items) -> indispensable pour exercer
        # un gate qui LIT le block de BASE du caster (ex. `AncestralFortuneAbility$$CanAddBlockChance`
        # = `StatAmount(self, 7, INITIAL) > 0`, #113).
        _patch_combat_stat(p_set, "BlockChance", "BlockDamage", a.block_player)
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
    if getattr(a, "armor_target", None) is not None:
        # ARMURE de la cible, forcée à une valeur CHOISIE (`Armor` + `FixedArmor` des a-units).
        # C'est le pendant MANQUANT de `--hp-target`, qui met l'armure à 0 et supprime donc
        # silencieusement l'étage armure (piège de mesure documenté dans runner.md §3).
        # POURQUOI ce levier existe : la branche PERÇAGE du plancher natif
        # `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
        # (`max(0, d - armure, d x pierce%)`) ne l'emporte QUE si `armure > d x (1 - pierce/100)` —
        # c'est le SEUL régime où le dégât réduit reste FRACTIONNAIRE, donc le seul où la
        # matérialisation finale (`Fix64.Round(., AwayFromZero)` vs `op_Explicit`) est OBSERVABLE.
        # Sur les profils à perçage BAS (Physical = 1 %), aucune armure du roster ne suffit :
        # sans ce levier la mesure R6 du canal `additional_hits` était INATTEIGNABLE.
        # Une valeur BASSE force au contraire la branche ARMURE (dégât ENTIER) = régime TÉMOIN
        # non discriminant.
        for u in bc.get("Units", []):
            if u.get("VisualId") in a_set:
                u["Armor"] = a.armor_target
                u["FixedArmor"] = a.armor_target
    for spec in (getattr(a, "unit_stat", None) or []):
        # Patch PER-UNIT des champs de `BC.Units`, appliqué au MÊME endroit (donc au même BC déjà
        # NORMALISÉ) que --hp-player/--dmg-target — qui, eux, ne savent forcer qu'une valeur unique
        # sur TOUT un camp. Sert les montages dont la mesure porte sur un ÉCART entre deux unités du
        # même côté : deux `Health` différents = deux niveaux d'utilité de soin/dégât sur des unités
        # par ailleurs identiques (#286 : discriminer un coefficient MULTIPLICATIF, qui exige deux
        # régimes à écart NON nul — un levier global ne peut par construction pas les produire).
        # Forme : "VisualId:Champ=Valeur[,Champ=Valeur][;VisualId:…]" ; la valeur est du JSON
        # (`80000`, `[]`, `null`) et le champ est écrit VERBATIM dans l'entrée Units.
        # La virgule sépare les champs SAUF à l'intérieur d'une valeur JSON composée
        # (`_split_hors_json` ci-dessus) : `Traits=["Summon","Decoy"]` est UNE valeur, pas deux
        # champs. Mesuré (#419-r7) : le `split(",")` naïf d'avant coupait cette valeur en
        # `'["Summon"'` et rendait `valeur non-JSON` — ce qui rendait INJOUABLE le bras UNION de
        # `#589-r1-r1-r2-r1-r2`, pourtant décrit comme « armé, confrontable sans rien de spécial ».
        for part in _split_hors_json(spec, ";"):
            part = part.strip()
            if not part:
                continue
            vis, _, fields = part.partition(":")
            vis = vis.strip()
            touched = [u for u in bc.get("Units", []) if u.get("VisualId") == vis]
            if not touched:
                print(f"[error] --unit-stat: VisualId '{vis}' absent du catalogue BC.Units",
                      file=sys.stderr)
                return 2
            for kv in _split_hors_json(fields, ","):
                key, _, val = kv.partition("=")
                key = key.strip()
                if not key:
                    continue
                try:
                    parsed = json.loads(val.strip())
                except json.JSONDecodeError:
                    print(f"[error] --unit-stat: valeur non-JSON pour {vis}.{key}: {val!r}",
                          file=sys.stderr)
                    return 2
                for u in touched:
                    u[key] = parsed
                if key == "Shield" and parsed:
                    # #342 -- MESURE, pas supposition : le champ est bien ECRIT dans le BC envoye
                    # a `initAndStart`, et le NATIF ne le lit jamais.
                    # `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` (la
                    # fonction qui REMPLIT chaque `BC.Units[]`) ecrit 29 champs et saute
                    # `UnitConfiguration.Shield@+0x4c` ;
                    # `IdunBattle.Operations.AddUnitOperation$$Execute` n'y accede pas ;
                    # `IdunBattle.Entities.Components.ShieldComponent$$.ctor` n'alloue qu'une
                    # `List` VIDE et son unique ecrivain
                    # (`...ShieldComponent$$AddOrUpdateShield`) n'a qu'un appelant,
                    # `IdunBattle.Operations.CreateShieldOperation$$Execute`.
                    # Sans ce warn le montage se lit comme un succes : ni erreur, ni bouclier.
                    print(f"[warn] --unit-stat {vis}:Shield={parsed} sera IGNORE au deploiement "
                          "(le natif ne lit jamais BC.Units[].Shield). Pour un bouclier REEL, "
                          "faire POSER le bouclier en bataille -- ex. `thousSorcerer` "
                          "(ArcaneShield) dans l'equipe de la cible ; cf. "
                          "docs/rl/case-342-shield-lever.md", file=sys.stderr)
            print(f"[build] --unit-stat {vis}: " + ", ".join(
                f"{kv.partition('=')[0].strip()}={touched[0].get(kv.partition('=')[0].strip())}"
                for kv in _split_hors_json(fields, ",") if kv.partition("=")[0].strip()))
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
    err = _apply_place_overrides(player_units, p_places, "--place")
    if err:
        print(f"[error] {err}", file=sys.stderr)
        return 2
    for uid, col, row in a_hand:
        player_units.append({"unitId": uid, "playerId": PLAYER_ID_AI,
                             "col": col, "row": row})
    placed = ([(u, c, r, 1) for u, c, r in p_places]
              + [(u, c, r, 2) for u, c, r in a_places])
    if placed:
        # REFUS AVANT le build : hors board / tuile injouable / deux unites sur la meme
        # tuile. Le runner n'est pas encore construit, donc rien a nettoyer -- alors
        # qu'un refus decouvert APRES laisse un runner enregistre sur le cap partage.
        bad = _validate_placements(bc, player_units, placed)
        if bad:
            for p in bad:
                print(f"[error] placement REFUSE: {p}", file=sys.stderr)
            print("[error] --place/--a-place: aucun runner n'a ete construit. "
                  "Choisir des tuiles dans le board et libres (voir board.py / "
                  "data/boards/ pour la geometrie).", file=sys.stderr)
            return 2
    for uid, col, row, team in placed:
        print(f"[build] place {uid} @({col},{row}) team{team}")
    # Replace SCOPE par acteur : cote hooks la coexistence est le DEFAUT
    # (initAndStart ne dispose plus jamais les runners freres ; cap dur
    # MAX_RUNNERS sinon refus explicite). Rebuild = remplacer LE runner
    # enregistre dans CE --state-file (celui que _save_state va ecraser),
    # pas les freres — sinon il deviendrait orphelin et mangerait le cap.
    if STATE.exists():
        # #379 -- LE site le plus dangereux du fichier. Ce `disposeRunner` frappe un id
        # relu sur DISQUE ; si le state-file vient d'une session anterieure (fenetre de
        # reinject), le compteur d'ids a redemarre a 0 et ce meme numero designe
        # aujourd'hui le runner d'un AUTRE agent : on le DETRUIRAIT sans qu'il en soit
        # informe. On ne dispose donc que sur estampille CONCORDANTE (ou sur un fichier
        # ecrit pendant la session courante). Le build lui-meme n'est PAS refuse : il est
        # precisement le geste « repartir a neuf », et il re-estampe le fichier.
        try:
            old = _read_state(STATE)
        except Exception:
            old = {}
        old_rid = old.get("runnerId")
        verdict = runner_state.verify(old, SESSION, STATE)
        if old_rid is not None and not verdict.ok:
            runner_state.enforce(verdict, "rl_duel build (dispose de l'ancien runner)")
            print(f"[build] ancien runner {old_rid} NON dispose (state-file d'une autre "
                  f"session) -- le state-file est reconstruit, cet id est laisse intact",
                  file=sys.stderr)
        elif old_rid is not None:
            runner_state.enforce(verdict, "rl_duel build (dispose de l'ancien runner)")
            _rpc(sid, "disposeRunner", [{"runnerId": old_rid}], timeout=15)
            print(f"[build] ancien runner {old_rid} du state-file dispose")
    # `owner` = le --state-file ABSOLU. C'est LA cle de proprietaire du harnais :
    # le registre cote hooks la garde telle quelle, si bien qu'un runner orphelin
    # se reconnait par recoupement avec les state-files vivants -- et non a l'age,
    # qui condamne aussi vite un runner legitime d'un agent lent.
    init_resp = _rpc(sid, "initAndStart",
                     [{"configJson": json.dumps(bc), "seed": a.seed,
                       "playerUnits": player_units,
                       "recordReplay": bool(getattr(a, "record_replay", False)),
                       "owner": str(STATE.resolve())}], timeout=40)
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
    if getattr(a, "record_replay", False):
        print("[build] replay recorder ARME (--record-replay) -> RPC replayOutputStream")
    print(f"[build] runnerId={rid}  MON roster (team 1)={p_units}")
    print(f"[build] roster ADVERSE (team 2)={a_units}{mow_str}")
    # UN SEUL `decisionView` pour les DEUX confrontations qui suivent (placements et roster) :
    # elles jugent le MEME instant, et deux releves distincts les feraient diverger sur un runner
    # qui bouge.
    dec_after = _decision(sid, rid)
    placement_problems: list[str] = []
    if placed:
        # Un placement refuse par le natif est un RETOUR NUL SILENCIEUX (cf. _verify_placements) :
        # sans cette confrontation, `build` rendrait 0 sur un montage qui n'a pas eu lieu.
        # Le verdict est POSE ICI mais RENDU tout a la fin, apres `_save_state` : sortir avant
        # d'ecrire le state-file laisserait ce runner ORPHELIN (le prochain build disposerait
        # l'ancien id, pas celui-ci) -- il mangerait le cap partage sans proprietaire.
        placement_problems = _verify_placements(sid, rid, [
            {"unitId": u, "col": c, "row": r, "team": t} for u, c, r, t in placed], dec=dec_after)
        if not placement_problems:
            print(f"[build] placements verifies OK ({len(placed)})")
    # #287-r13 : le ROSTER, que la confrontation ci-dessus ne visite pas (elle ne juge que les
    # unites CITEES par --place/--a-place). Toujours joue, meme sans placement.
    roster_problems = _verify_roster(dec_after, p_units, a_units)
    modifier_problems: list[str] = []
    if unit_mods:
        # Meme raison d'etre que la confrontation des placements : `ApplyModifiers`
        # n'emet rien vers l'appelant, et le runner de test utilise un NullLogger --
        # sa branche d'erreur est donc muette. On RELIT l'etat.
        modifier_problems = _verify_unit_modifiers(sid, rid, unit_mods)
    if a.advance > 0:
        _advance(sid, rid, a.advance, a.maxpump)
        print(f"[build] advanced {a.advance} tours (IA vs IA)")
    res = _show_card(sid, rid, bc)
    my_team = next((u.get("team") for u in (res.get("units") or [])
                    if u.get("ctrl")), None)
    _save_state({"runnerId": rid, "bc": bc, "seed": a.seed, "myTeam": my_team,
                 "playerUnits": player_units})
    # #287-r13-r1 : le refus est desormais DUR (rc 3), comme celui des placements -- et il l'est
    # sur une MESURE, pas sur un principe (`probe_287r13r1_rayon_refus_roster.py`) :
    #
    #   * RAYON     : 16 sites sur 245 invocations qui montent une bataille (6,5 %) lisent le `rc`
    #                 (2 `check=True`, 14 `.returncode`). Les 229 autres ne lient meme pas le
    #                 resultat de `subprocess.run` -- et le `return 3` ci-dessous arrive APRES
    #                 `_save_state`, donc le runner existe et le state-file est ecrit : un
    #                 appelant qui n'inspecte pas le `rc` poursuit EXACTEMENT comme avant.
    #                 Les 14 `--list-pool` sont hors de portee : ils n'atteignent pas ce code.
    #   * FREQUENCE : 0 deficit sur 8 montages representatifs (roster aleatoire, MoW,
    #                 multiplicites x4 et x6, 5v5, 1v1, board etroit) -- le cas extreme est
    #                 d'ailleurs deja refuse EN AMONT par le garde de capacite de spawn JOUEUR
    #                 (`N spawns joueur < M units`, rc 2). Le deficit residuel vient du cote
    #                 ADVERSE, confie au placement natif, qui n'a pas ce garde.
    #
    # Le risque reel est le PRODUIT des deux, jamais l'un des deux seul.
    #
    # ECHAPPATOIRE CONSCIENTE, et par ENV plutot que par drapeau : un appelant que ce refus
    # bloquerait est un probe deja ecrit, souvent celui d'un autre agent -- lui demander de
    # modifier son fichier pour se debloquer, c'est lui faire payer notre cliquet. La variable
    # se pose devant la commande. Meme forme que `TACTICUS_ALLOW_GREEN_SKIP` (#455).
    allow_roster_deficit = os.environ.get("TACTICUS_ALLOW_ROSTER_DEFICIT") == "1"
    if roster_problems:
        for p in roster_problems:
            print(f"[error] roster NON MONTE: {p}", file=sys.stderr)
        print("[error] --p-units/--a-units: le roster DEMANDE n'est pas celui qui est en "
              "bataille. Causes connues, toutes a RETOUR NUL SILENCIEUX cote natif : tuile "
              "interdite/occupee (AddUnitOperation$$AreTilesDisallowedAndLog), reservee, en "
              "attente de draft, sous brouillard -- et, pour une unite confiee au placement "
              "NATIF, un SpawnPointGroup trop petit "
              "(SetupGameOperation$$AddPredefinedUnits). La geometrie mesuree n'est PAS celle "
              "demandee.", file=sys.stderr)
        print("[error] Si ce montage-la est VOULU tel quel, poser "
              "TACTICUS_ALLOW_ROSTER_DEFICIT=1 devant la commande -- le refus est alors LEVE "
              "et le deficit reste imprime.", file=sys.stderr)
        if allow_roster_deficit:
            print("[warn] TACTICUS_ALLOW_ROSTER_DEFICIT=1 : refus LEVE, rc inchange. La "
                  "geometrie mesuree n'est toujours PAS celle demandee.", file=sys.stderr)
    if placement_problems:
        for p in placement_problems:
            print(f"[error] placement NON HONORE par le natif: {p}", file=sys.stderr)
        print("[error] --place/--a-place: le runner est construit ET enregistre dans le "
              "state-file, mais le montage demande n'a PAS eu lieu -- tuile interdite ou "
              "occupee (AreTilesDisallowedAndLog), reservee (TilesAreReserved), en attente "
              "de draft (TilesArePendingDrafting) ou sous brouillard (TilesAreInFog) : les "
              "quatre font un retour NUL SILENCIEUX dans "
              "IdunBattle.Operations.AddUnitOperation$$Execute.", file=sys.stderr)
    if modifier_problems:
        for p in modifier_problems:
            print(f"[error] unit-modifier NON HONORE par le natif: {p}", file=sys.stderr)
        print("[error] --unit-modifier: le runner est construit ET enregistre dans le "
              "state-file, mais le montage demande n'a PAS eu lieu.", file=sys.stderr)
    # Les TROIS diagnostics sont imprimes AVANT tout retour : un montage peut echouer sur
    # plusieurs axes a la fois, et sortir au premier cacherait les suivants -- l'appelant
    # relancerait pour decouvrir le second. (Avant #287-r13-r1, `placement_problems` rendait 3
    # sans jamais laisser parler `modifier_problems`.)
    if placement_problems or modifier_problems or (roster_problems and not allow_roster_deficit):
        return 3
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
            # #411-r2 — L'AUTO-RÉSOLUTION NE DEVINE PLUS. `attackPlans` porte UNE entrée par
            # ABILITY castable sur cette cible (`decisionView` est appelé `allAbilities=True`
            # par `_decision`) : pour un caster qui a une active ciblable, la liste contient
            # l'attaque NORMALE **et** l'active. La boucle d'origine n'avait pas de `break` —
            # elle retenait donc la DERNIÈRE, c'est-à-dire l'ACTIVE, en silence.
            #
            # MESURÉ (#411-r2, `probe_411r2_stage_sweep.py`) : sur `necroDestroyer` →
            # `astraBullgryn`, les evals sont [69 Loki_NormalAttack (normal),
            # 1006 MultiThreatEliminator (active)]. Les probes qui croyaient confronter
            # l'attaque normale faisaient donc jouer au natif l'ACTIVE, pendant que leur port
            # résolvait `AttackDamageOperation.execute`. L'écart qui en résultait se lisait
            # comme une divergence de port : port 426 / natif 3433, « x8,06 ». Avec
            # `--ability 69` explicite, le même montage rend 426 / 349 — l'écart n'existe pas.
            # `MultiThreatEliminator` étant CONFIG-based, son dégât ne bouge pas quand on
            # change `Damage` de l'attaquant (9/18/36 → natif constant), ce qui rendait le
            # symptôme d'autant plus déroutant.
            #
            # Le même piège était DÉJÀ connu et paré ailleurs : `_normal_ability_map` (TF18)
            # existe précisément pour ne pas « se fier au défaut (qui peut résoudre vers un
            # ACTIF) », mais elle ne servait qu'à `play`/`_apply_spec`, pas à `act`.
            #
            # On LÈVE au lieu de choisir : rendre un résultat sur une ability arbitraire est
            # exactement ce qui se lit comme une mesure. Un seul candidat -> comportement
            # inchangé.
            cands = []
            for p in (res.get("attackPlans") or []):
                if p.get("unitId") == a.caster:
                    for ev in (p.get("evals") or []):
                        if ev.get("targetId") == a.target and ev.get("abilityId") is not None:
                            if ev["abilityId"] not in [c[0] for c in cands]:
                                cands.append((ev["abilityId"], ev.get("ability"),
                                              ev.get("kind")))
            if len(cands) > 1:
                normal_id = _normal_ability_map(res).get(a.caster)
                print(f"[act] AMBIGU : {len(cands)} abilities castables u{a.caster}->"
                      f"u{a.target} — l'auto-resolution ne choisit PAS. Passe --ability :")
                for aid, nm, kd in cands:
                    star = "  <- attaque NORMALE" if aid == normal_id else ""
                    print(f"         --ability {aid}   {nm} [{kd}]{star}")
                return 2
            if cands:
                ability = cands[0][0]
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
    # À PARTIR D'ICI L'ACTION EST APPLIQUÉE : plus rien ne doit interrompre la
    # comptabilité (action_log + _save_state). `_print_apply` rend sa panne de
    # décodage au lieu de la lever — cf. sa docstring et #254b-a.
    decode_err = _print_apply(label, r, my_ids)
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
    if decode_err:
        # rc != 0 pour que l'échec soit RENDU, mais APRÈS la sauvegarde d'état et
        # avec la consigne explicite : l'action a eu lieu, la relancer la jouerait
        # DEUX FOIS.
        print("  [act] /!\\ ACTION APPLIQUEE mais compte rendu NON DECODE (%s)." % decode_err)
        print("  [act] /!\\ NE PAS REJOUER cette action. Etat reel : `rl_duel.py view`.")
        return 3
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
    try:
        for ev in (act.get("events") or []):
            if stream_events.step_name(ev.get("step")) in meaningful:
                return True
    except Exception as e:
        # Table d'enums indisponible : on ne SAIT PAS. Ne jamais transformer un
        # « je n'ai pas pu decoder » en « l'ability a rate » -- le verdict remonte
        # dans `_action_failed`, qui ferait sauter l'append `action_log` d'une action
        # DEJA appliquee (le piege de #254b-a). On rend le doute au benefice du reel.
        print("  [act] /!\\ decodage des events impossible (%s: %s) -> effet reel INDECIDABLE,"
              " suppose OUI" % (type(e).__name__, e))
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
    # Panne de DÉCODAGE d'un compte rendu (≠ échec d'action) : jamais un abandon —
    # les actions sont appliquées. Signalée à la fin, sans annuler la trajectoire.
    decode_errs: list[str] = []
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
        # Idem cmd_act : passé ce point l'action EST appliquée, le décodage ne lève plus.
        derr = _print_apply(label, r, my_ids)
        if derr:
            decode_errs.append(f"{label} -> {derr}")
        fail = _action_failed(r, "ability" if k == "normal" else k, sid, rid, action)
        if fail:
            aborted = f"{label} -> {fail}"; break
        # action RÉUSSIE -> log live (pour replay-to-state du guard). Per-action +
        # save : robuste aux tours splittés sur plusieurs `play` (un re-send d'une
        # action déjà jouée échoue côté engine -> pas re-loggé, pas de doublon).
        st["action_log"].append(action)
        _save_state(st)
    if decode_errs:
        print("  [play] /!\\ %d compte(s) rendu(s) NON DECODE(S) -- les actions ONT ete"
              " APPLIQUEES et LOGGEES, ne pas les rejouer :" % len(decode_errs))
        for d in decode_errs:
            print("    - " + d)
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
    src_path = Path(a.attach_from)
    src = _read_state(src_path)
    # #379 : le `--from` est un state-file comme un autre -- il porte un `runnerId` de
    # l'espace d'ids PARTAGE. L'attacher sans le confronter recopierait un id perime dans
    # un state-file NEUF, et lui donnerait une estampille FRAICHE : le mensonge deviendrait
    # indetectable en aval. On refuse ici, a la copie.
    if not runner_state.enforce(runner_state.verify(src, SESSION, src_path),
                                "rl_duel attach (--from)"):
        return 2
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
    ap.add_argument("--bis-items", action="store_true",
                    help="build: EQUIPE chaque unite de ses items Best-In-Slot "
                         "avant la formule de stats (#419-r5). C'est DESORMAIS LE "
                         "DEFAUT (#419-r6) -- le drapeau reste accepte comme no-op "
                         "explicite. Les 4 stats CritChance/CritDamage/BlockChance/"
                         "BlockDamage ne vivent QUE dans les items (cf. `itemSlots` du "
                         "gameconfig) : sans eux "
                         "`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` "
                         "(GetStat(9) > 0 && GetStat(10) > 0) est FAUX pour toute "
                         "unite -- cote natif COMME cote port. Mesure au rank 17 : "
                         "could_crit 0/106 -> 98/106, could_block 0/106 -> 46/106.")
    ap.add_argument("--no-bis-items", action="store_true",
                    help="build: N'EQUIPE PAS -- restitue le regime d'AVANT #419-r5, ou "
                         "le crit et le block sont structurellement impossibles sur "
                         "TOUTE unite. C'est le TEMOIN de la bascule #419-r6, pas un "
                         "mode de travail : un heros rank 17 / level 50 / 5 etoiles sans "
                         "aucun item n'existe pas dans le jeu. Equivalent global sans "
                         "toucher a la ligne de commande : TACTICUS_BIS_ITEMS=0.")
    ap.add_argument("--record-replay", action="store_true",
                    help="build: ARME l'enregistreur de replay NATIF sur le runner "
                         "(#477-r1). Sans lui, `IdunBattle.Runner.IdunRunner$$Initialize` "
                         "saute `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder` et le RPC "
                         "`replayOutputStream` rend un flux VIDE sans erreur. Cout: retention du "
                         "texte de stream + un objet par tirage PRNG pour toute la bataille -- "
                         "a n'armer que pour lire le flux.")
    ap.add_argument("--seed-bc", default=None,
                    help="build: chemin d'un seed BC CUSTOM (surcharge data/seed-bc.json). Sert a "
                         "valider un porteur HORS pool (ex. bloodTerminator/SavageEchoes) en injectant "
                         "son bloc Unit dans une copie du seed BC. N'ecrit jamais le seed BC partage.")
    ap.add_argument("--crit", default=None,
                    help="build: force CritChance,CritDamage sur les p-units (ex. '100,700'). "
                         "Sert dans les DEUX sens (#914) : monter le crit pour l'exercer, et le "
                         "poser a '0,0' pour construire un porteur qui n'en a PAS -- depuis "
                         "#419-r5 les items BiS sont equipes par defaut et le crit n'est PLUS "
                         "strippe par la normalisation (could_crit 0/106 -> 98/106), donc un "
                         "montage qui SUPPOSE un zero mesure autre chose que ce qu'il croit.")
    ap.add_argument("--crit-target", default=None, help="build: idem --crit pour les a-units")
    ap.add_argument("--block-target", default=None,
                    help="build: force BlockChance,BlockDamage sur les a-units (ex. '100,500')")
    ap.add_argument("--block-player", default=None,
                    help="build: idem --block-target mais pour les p-units (block de BASE du caster — "
                         "requis pour exercer un gate qui lit StatAmount(self, BlockChance, INITIAL))")
    ap.add_argument("--hp-target", type=int, default=None,
                    help="build: force Health+RemainingHealth des a-units (PV bas = kill déterministe) "
                         "ET MET Armor/FixedArmor A 0 — piège de mesure : cela SUPPRIME l'étage armure, "
                         "donc tout régime où la branche perçage du plancher mordrait")
    ap.add_argument("--hp-player", type=int, default=None,
                    help="build: idem --hp-target mais pour les p-units (mover fragile côté joueur) — "
                         "MET AUSSI Armor/FixedArmor a 0, même piège de mesure")
    ap.add_argument("--unit-stat", action="append", default=None,
                    help="build: patch PER-UNIT du BC normalise, "
                         "'VisualId:Champ=Valeur[,Champ=Valeur][;VisualId:...]' (valeur JSON). "
                         "Repetable. Pendant per-unit de --hp-player/--dmg-target, qui forcent une "
                         "valeur unique sur tout un camp : indispensable des que la mesure porte sur "
                         "un ECART entre deux unites du meme cote (ex. deux Health -> deux niveaux "
                         "d'utilite de soin). Pas de virgule dans une valeur.")
    ap.add_argument("--explicit-stats", action="append", default=None, metavar="UNITID",
                    help="build: amene un porteur NPC ou SUMMON avec SES PROPRES stats, traits et "
                         "armes (#419-r1-tr12-r2), repetable. La formule heros "
                         "IStatsFormula.StatsUsingProgressionIndexFor LEVE sur ces unites (aucune "
                         "table de progression de heros) : elles finissaient en `skipped`, hors "
                         "pool, et leurs mecaniques n'etaient confrontables que par GREFFE de "
                         "l'ability sur un heros. Les stats sont calculees par le chemin natif de "
                         "leur categorie -- npc: UnitProgression$$GetNpcStats (table "
                         "units.npc[id].stats[], palier = suffixe ':<n>' de l'id, DEFAUT 1) ; "
                         "summon: UnitProgression$$GetSummonStats (variables summon* de l'ability "
                         "invocatrice). L'entree de catalogue est injectee si elle manque. "
                         "Ex. --explicit-stats admecNpc3Electropriest:33")
    ap.add_argument("--equip-relic", action="append", default=None,
                    help="build: EQUIPE une relique — 'unitId:AbilityName[:level]', repetable. "
                         "Pose BC.Units[].TertiaryAbility + TertiaryAbilityLevel (>=1 OBLIGATOIRE : "
                         "Idun.Shared.Level$$ToZeroBasedIndex leve sur <=0) ET injecte la config "
                         "d'ability dans BC.Abilities.PassiveAbilities (29 des 32 abilities de "
                         "relique sont absentes du seed capture). Le porteur est injecte au "
                         "catalogue s'il manque (#237-r1 : 5 des 32 reliques n'ont AUCUN porteur "
                         "au seed BC), donc l'ETAT 3 de la gate tient en UNE commande. "
                         "Ids/porteurs : `python catalog_inject.py --list-relics`.")
    ap.add_argument("--allow-unlisted-relic", action="store_true",
                    help="build: --equip-relic sur un porteur hors allowedUnits (greffe assumee)")
    ap.add_argument("--equip-mythic", action="append", default=None,
                    help="build: DEBLOQUE la mythique d'une Machine of War (#999) — "
                         "'unitId[:AbilityName[:level]]', repetable ; l'ability est DERIVEE du "
                         "porteur si elle est omise (chaque MoW n'en porte qu'une). MEME voie "
                         "tertiaire que --equip-relic cote bataille (UnitFactory$$"
                         "AddConfiguredAbilities n'a qu'UNE tertiaire) : pose TertiaryAbility + "
                         "TertiaryAbilityLevel (>=1 OBLIGATOIRE) et injecte la config dans "
                         "BC.Abilities.PassiveAbilities — les 11 mythiques sont TOUTES absentes du "
                         "seed capture. Le porteur est injecte au catalogue s'il manque (plusieurs "
                         "MoW mythiques sont hors pool). Porteurs : "
                         "`python catalog_inject.py --list-mythics`.")
    ap.add_argument("--allow-unlisted-mythic", action="store_true",
                    help="build: --equip-mythic sur une unite dont mythicAbilities ne porte pas "
                         "cette ability (greffe assumee)")
    ap.add_argument("--armor-target", type=int, default=None,
                    help="build: force Armor+FixedArmor des a-units a la valeur donnee (pendant "
                         "de --hp-target, qui les met a 0). HAUTE = la branche PERCAGE du plancher "
                         "l'emporte -> degat FRACTIONNAIRE, seul regime ou la materialisation "
                         "finale (Round vs troncature) est observable ; BASSE = branche ARMURE, "
                         "degat entier, regime TEMOIN non discriminant")
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
    ap.add_argument("--place", action="append", default=None,
                    help="build: place une unite de MON roster sur une TUILE EXACTE -- "
                         "'unitId:col,row', repetable (une entree par occurrence de l'id). "
                         "Sans lui, les p-units prennent les SpawnPoints du board dans l'ordre. "
                         "Le natif (IdunBattle.Operations.AddUnitOperation$$Execute) n'exige PAS "
                         "que la tuile appartienne au SpawnPointSet : ses gardes sont "
                         "AreTilesDisallowedAndLog / TilesAreReserved / TilesArePendingDrafting / "
                         "TilesAreInFog, et chacune fait un RETOUR NUL SILENCIEUX -> hors board / "
                         "tuile injouable / collision sont REFUSES avant le build, et la position "
                         "obtenue est VERIFIEE apres.")
    ap.add_argument("--a-place", action="append", default=None,
                    help="build: idem --place pour une unite du roster ADVERSE. L'unite est SORTIE "
                         "de BC.PredefinedUnits (que le natif place lui-meme sur le "
                         "SpawnPointGroup) et posee par AddUnitMessage(playerId=12) sur la tuile "
                         "demandee. Meme verification qu'au --place. ATTENTION: sortie des "
                         "PredefinedUnits, elle n'est plus eligible a --unit-modifier.")
    ap.add_argument("--unit-modifier", action="append", default=None,
                    help="build: modifie une stat d'une unite PREDEFINIE adverse par le point "
                         "d'entree NATIF BC.UnitModifiers -- 'unitId:Id:Amount', repetable. Id parmi "
                         "dmg / fixedArmor / movement / hits / hp / blockChance / critDmg / "
                         "critChance (les seuls que "
                         "IdunBattle.Operations.SetupGameOperation$$ApplyModifiers dispatche ; tout "
                         "autre part dans sa branche de log et n'applique RIEN). Produit de VRAIS "
                         "StatModifier, la ou --unit-stat reecrit un scalaire du template "
                         "BC.Units[]. Amount = POURCENTAGE pour dmg/fixedArmor/hp/critDmg, ABSOLU "
                         "pour movement/hits/blockChance/critChance. Cas particulier : "
                         "'<u>:hp:<N>' avec N > 99 EMPECHE le deploiement de l'unite "
                         "(IsPredefinedUnitDisabledByModifiers).")
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
        # CHOKE POINT (#349) : un state-file est une SORTIE de run. `data/` est
        # VERSIONNE et ne porte que des ENTREES -- y ecrire salit `git status`,
        # le signal dont l'isolation par worktree se sert comme garde-fou. Le
        # refus vit ICI, pas chez les appelants : il couvre aussi ceux que le
        # cliquet statique de probe_273 ne balaye pas (workflows JS).
        try:
            host_inputs.reject_data_output(a.state_file, "--state-file")
        except host_inputs.DataOutputRefused as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
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
    # #379 : identite COMPLETE de la session (id + pid + startedAt), pas seulement `sid`.
    # `nextSessionId` est un etat de module du HOST -- un restart du host le remet a 1, si
    # bien que deux sessions distinctes peuvent porter le meme `id` et qu'une estampille
    # reduite a l'id VALIDERAIT un state-file mort. `startedAt` (ISO a la milliseconde)
    # tranche. Identite illisible -> `stamp` n'ecrit rien et `verify` rend UNSTAMPED : on
    # ne fabrique jamais une estampille a partir d'une inconnue.
    global SESSION
    SESSION = runner_state.current_identity()
    if SESSION is None:
        print("[warn] identite de session ILLISIBLE (/api/admin/status) -- les "
              "state-files ne seront ni estampes ni verifies (#379)", file=sys.stderr)
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
