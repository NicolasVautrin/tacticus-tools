"""probe #226 -- le seed BC injecte a la main n'embarque que le bloc `Units`, PAS les CONFIGS
D'ABILITY (`BattleConfiguration.Abilities`) -> faux « system error » au cast.

CE QUE CA TRANCHE (question binaire). Une unite injectee dans une COPIE du seed BC peut-elle caster
ses abilities ? Le residu documente jusqu'ici (« le cast live de 1230 leve system error, limite du
harnais out-of-pool ») accusait le RANG / la non-materialisation des arrays de variables. FAUX : la
cause est que `BattleConfiguration.Abilities.ActiveAbilities["SavageEchoes"]` N'EXISTE PAS dans le
seed capture (131 actives / 194 passives = uniquement les abilities des unites de CETTE bataille).
`IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` est alors appele sur une config
nulle -> faute d'invoke il2cpp remontee a l'appelant en « system error ».

DECOMPOSITION PAR ETAGE -- une SEULE variable change entre deux montages consecutifs :
  A `clone`     : bloc Unit clone d'une unite de la meme faction, AUCUNE config d'ability ajoutee
                  (= etat AVANT correctif, tel qu'ecrit dans test_savage_echoes_live.py /
                  test_sky_strike_live.py) ;
  B `clone-cfg` : MEME bloc Unit clone, + les configs d'ability de `catalog_inject.synthesize_ability`
                  -> isole la config comme SEULE cause (le bloc Unit est bit-identique a A) ;
  C `inject`    : la voie du correctif -- `catalog_inject.augment` (mirror de
                  `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`) qui pose
                  `BC.Units` ET `BC.Abilities`.

Chaque montage : build runner isole -> Cezare (ou Celestine) rendue adjacente a une cible -> cast de
l'ability -> on imprime `ok` et l'`error` NATIVE. Attendu : A KO, B OK, C OK.

Usage :
  python probe_226_seed_bc_ability_configs.py                 # bloodTerminator / SavageEchoes 1230
  python probe_226_seed_bc_ability_configs.py --unit adeptCelestine --ability 1025 --clone-base adeptCanoness
ASCII only.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import catalog_inject as CI
import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs" / "runners"
BOARD = "MC1_67"
SEED = 777
A_UNITS = "necroWarden,necroDestroyer,necroWarden,necroOverlord"
DUMP_TAGS = False               # --dump-tags : stats caster/cible + tags bruts des coups


# --------------------------------------------------------------------------- seeds BC

def _clone_unit(seed: dict, unit_id: str, clone_base: str, ability: int) -> dict:
    """Le bloc Unit tel que les tests le fabriquaient : COPIE d'une unite deja au catalogue, ids
    reecrits, abilities reduites a celle qu'on teste. AUCUNE config d'ability ajoutee."""
    base = next((u for u in (seed.get("Units") or []) if u.get("VisualId") == clone_base), None)
    if base is None:
        raise SystemExit("[226] unite a cloner absente du seed BC: %s" % clone_base)
    inj = copy.deepcopy(base)
    inj.update({"Id": unit_id, "VisualId": unit_id, "QuestUnitId": unit_id,
                "ActiveAbilities": [ability], "PassiveAbilities": [],
                "ConfigId": {"PureId": unit_id, "Rarity": None, "Level": None,
                             "IsBorrowed": False, "IsPvpOpponent": False}})
    return inj


def _write(bc: dict, tag: str, withheld=()) -> Path:
    """Ecrit le seed BC ET son sidecar (#380), toujours -- meme vide.

    POURQUOI LE SIDECAR EST OBLIGATOIRE ICI. `rl_collect_batch._load_seed_bc` applique
    `catalog_inject.refresh_ability_configs`, dont la 2e boucle POSE toute config qu'une entree
    `Units` reclame au gameconfig. Le bras `clone` de ce probe -- dont le POINT est justement
    l'absence de config -- repartait donc du chargeur avec `SavageEchoes` et `RedRampage` en
    place : les TROIS bras livraient la meme chose au runner, et la discrimination A KO / B OK /
    C OK avait disparu. Mesure et recensement : `probe_380_seed_bc_patch_survival.py --measure`.
    Le verdict #226 reste juste (mesure le 2026-07-29 a 00h38, rattrapage #254 pose a 19h17 le
    meme jour) : c'est la REPRODUCTIBILITE qui etait perdue, pas la conclusion.
    Le sidecar est ecrit meme vide : un fichier de tag reutilise garderait sinon la retenue du
    run precedent, et un bras temoin serait retenu a son tour, en silence.
    """
    p = LOGS / ("bc-226-%s.json" % tag)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    CI.write_pins(p, [], withheld=withheld)
    return p


def _strip_ability_configs(bc: dict, unit_id: str) -> list:
    """RETIRE du BC les configs d'ability du kit de `unit_id` et rend leurs cles `"<node>/<nom>"`.

    C'est exactement l'absence que le bras `clone` veut faire mesurer au natif : l'unite EXISTE au
    catalogue, ses ids d'ability sont dans son entree `Units`, mais `BC.Abilities` ne porte AUCUNE
    config pour eux -> `AbilitiesDatabase.GetConfig` rend une config vide et le cast leve.

    ⚠ IL FALLAIT LA RETIRER, PAS LA CONSTATER ABSENTE (#10039). Cette fonction ENUMERAIT les
    configs manquantes -- ce qui marchait tant que `data/seed-bc.json` etait la capture d'UNE
    bataille, dont `BC.Abilities` ne portait que les abilities des unites presentes. Le catalogue
    est desormais FORGE par `Idun.Source.IdunBattle.View.BattleConfigBuilder` et porte TOUT le
    roster : plus aucune config ne manque, l'enumeration rendait `[]`, et le bras `clone` livrait
    au runner exactement la meme chose que ses deux temoins. La discrimination A KO / B OK / C OK
    avait disparu une SECONDE fois, par une autre porte que #375 -- meme signature : un bras
    negatif neutralise en silence, donc un run vert qui ne mesure rien.

    Le sidecar `withheld` (#380) reste indispensable APRES le retrait : sans lui la 2e boucle de
    `refresh_ability_configs` reposerait au chargement toute config qu'une entree `Units` reclame.
    """
    act, pas = CI._ability_names(unit_id)
    node = bc.get("Abilities") or {}
    out = []
    for names, key in ((act, "ActiveAbilities"), (pas, "PassiveAbilities")):
        have = node.get(key)
        for n in names:
            out.append("%s/%s" % (key, n))
            if isinstance(have, dict):
                have.pop(n, None)
    return sorted(out)


def build_seed(mode: str, unit_id: str, clone_base: str, ability: int, tag: str) -> Path:
    seed = CI._load_seed(None)
    if mode == "inject":
        bc, _added, added_ab, _unres = CI.augment(seed, [unit_id])
        for u in bc["Units"]:
            if u.get("Id") == unit_id:
                u["ActiveAbilities"] = [ability]
                u["PassiveAbilities"] = []
        print("[%s] configs d'ability posees: %s" % (mode, added_ab))
        return _write(bc, tag)
    bc = copy.deepcopy(seed)
    # ⚠ Le clone REMPLACE l'entree homonyme au lieu de s'y ajouter (#10039). Depuis que le
    # catalogue est forge, `unit_id` y est DEJA : `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig`
    # parcourt `BC.Units` et rend la PREMIERE entree dont l'`Id` matche -- le clone pose en queue
    # ne serait donc jamais lu, et les trois bras redeviendraient indiscernables.
    garde = [u for u in (bc.get("Units") or []) if u.get("Id") != unit_id]
    bc["Units"] = garde + [_clone_unit(seed, unit_id, clone_base, ability)]
    if mode == "clone-cfg":
        act, pas = CI._ability_names(unit_id)
        node = bc.setdefault("Abilities", {})
        added = []
        for names, key in ((act, "ActiveAbilities"), (pas, "PassiveAbilities")):
            tgt = node.setdefault(key, {})
            for n in names:
                if n not in tgt:
                    tgt[n] = CI.synthesize_ability(n)
                    added.append(n)
        print("[%s] configs d'ability posees: %s" % (mode, added))
        return _write(bc, tag)
    withheld = _strip_ability_configs(bc, unit_id)
    print("[%s] configs d'ability RETIREES du catalogue (etat AVANT correctif) ; RETENUES au "
          "chargement (#380): %s" % (mode, withheld))
    return _write(bc, tag, withheld=withheld)


# --------------------------------------------------------------------------- runner

def _build_runner(bc_file: Path, unit_id: str, tag: str):
    state = LOGS / ("rs-226-%s.json" % tag)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--state-file", str(state),
         "--seed-bc", str(bc_file), "--board", BOARD, "--roster", "1",
         "--p-units", unit_id, "--a-units", A_UNITS, "--hp-target", "300000"],
        cwd=str(HERE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("[226] build KO: %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return None, state
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"]), state


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _drive_adjacent(rid, unit_id):
    """Amene le caster a son tour, puis colle une cible ennemie sur une tuile voisine libre."""
    from engine.entities.pathfinding.board import Board
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None, None, None
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = me = None
    for _ in range(14):
        dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
        me = _find(dv, unit_id)
        if me is not None and dv.get("currentPlayer") == me.get("owner"):
            break
        L._rpc("aiPlayTurn", [{"runnerId": rid}])
    if me is None:
        return None, None, None
    tgt = next((u for u in (dv.get("units") or [])
                if u.get("alive") and u.get("owner") != me.get("owner")), None)
    if tgt is None:
        return None, None, None
    mp = me.get("pos") or {}
    tid = board.id_at(mp.get("col"), mp.get("row"))
    occ = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dv.get("units") or []) if u.get("alive")}
    dest = next((n for n in board.neighbours(tid)
                 if board.walkable(n) and board.coord(n) not in occ), None)
    if dest is None:
        return None, None, None
    dc = board.coord(dest)
    L._rpc("applyAction", [{"runnerId": rid, "action": {
        "kind": "move", "unitId": tgt["id"], "to": {"col": dc[0], "row": dc[1]}}}])
    return board, me["id"], tgt["id"]


def run_mode(mode: str, unit_id: str, clone_base: str, ability: int) -> dict:
    tag = "%s-%s" % (mode, uuid.uuid4().hex[:6])
    print("=== montage %s ===" % mode)
    bc_file = build_seed(mode, unit_id, clone_base, ability, tag)
    rid, state = _build_runner(bc_file, unit_id, tag)
    out = {"mode": mode, "runner": rid, "ok": None, "errors": None}
    try:
        if rid is None:
            return out
        board, cid, tid = _drive_adjacent(rid, unit_id)
        if cid is None:
            print("[%s] drive KO (geometrie / caster absent)" % mode)
            return out
        cast = L._rpc("applyAction", [{"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ability},
            "captureEvents": True}])
        out["ok"] = bool(isinstance(cast, dict) and cast.get("ok"))
        out["errors"] = [a.get("error") for a in (cast.get("actions") or []) if a.get("error")]
        if not out["errors"] and isinstance(cast, dict) and cast.get("error"):
            out["errors"] = [cast.get("error")]
        dmg = []
        for a in (cast.get("actions") or []):
            for ev in (a.get("events") or []):
                tags = ev.get("tags")
                if not tags:
                    continue
                td = json.loads(tags) if isinstance(tags, str) else tags
                if td.get("Active_Ability_Type") == ability and "Amount" in td:
                    dmg.append(td.get("Amount"))
        out["hits"] = dmg
        print("[%s] cast ok=%s errors=%s hits=%s" % (mode, out["ok"], out["errors"], dmg))
        if DUMP_TAGS:
            snap = L._rpc("combatSnapshot", [{"runnerId": rid}])
            for u in (snap.get("units") or []):
                if u.get("id") in (cid, tid):
                    st = u.get("stats") or u
                    print("  [stats] id=%s %s" % (u.get("id"), json.dumps(st)[:600]))
            for a in (cast.get("actions") or []):
                for ev in (a.get("events") or []):
                    tags = ev.get("tags")
                    if not tags:
                        continue
                    td = json.loads(tags) if isinstance(tags, str) else tags
                    if td.get("Active_Ability_Type") == ability:
                        print("  [tag] %s" % json.dumps(td)[:600])
    finally:
        if rid is not None:
            try:
                L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:
                pass
        for p in (bc_file, CI.pins_path(bc_file), state):
            try:
                p.unlink()
            except Exception:
                pass
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="probe #226 seed BC / configs d'ability")
    ap.add_argument("--unit", default="bloodTerminator")
    ap.add_argument("--clone-base", default="bloodDeathCompany")
    ap.add_argument("--ability", type=int, default=1230)
    ap.add_argument("--modes", default="clone,clone-cfg,inject")
    ap.add_argument("--dump-tags", action="store_true",
                    help="stats caster/cible + tags bruts des coups (diagnostic crit/block)")
    a = ap.parse_args(argv)
    global DUMP_TAGS
    DUMP_TAGS = a.dump_tags
    rows = [run_mode(m.strip(), a.unit, a.clone_base, a.ability)
            for m in a.modes.split(",") if m.strip()]
    print("=== SYNTHESE #226 (%s / ability %d) ===" % (a.unit, a.ability))
    for r in rows:
        print("  %-10s cast_ok=%-5s errors=%s hits=%s"
              % (r["mode"], r["ok"], r.get("errors"), r.get("hits")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
