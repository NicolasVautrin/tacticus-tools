"""Probe #354 -- MESURE : qui porte `MartialApotheosis` (1045), et que tire reellement le
turn-start de `necroOverlord` ?

CONTEXTE. `tests/engine/runner/test_martial_apotheosis_live.py` rougit sur trois de ses cinq
tests -- exactement les trois qui passent par `start_turn_triggers`, qui rend une liste VIDE.
Les deux qui appellent le port DIRECTEMENT (`matches`, `execute_behaviour`) passent. Le
decrochage n'est donc ni dans l'arbre DSL, ni dans le rail de dispatch : il est a l'etage
ATTRIBUTION -- `collect_triggered_abilities` (dispatch/core.py) instancie une ability-trigger
UNIQUEMENT si `gameconfig.unit(visualId).passiveAbilities` la nomme.

CE QUE CE PROBE MESURE, en trois etages, sans rien supposer :

  ETAGE 1 (offline, gameconfig) -- balaye les TROIS sections d'unites (`lineup`, `npc`,
      `summons`) de CHAQUE instantane de gameconfig present sur la machine, et compte les
      porteurs de `MartialApotheosis` par voie d'attribution. Balayer tous les instantanes
      (pas seulement l'actif) distingue « le jeu vient de retirer l'ability » d'un artefact
      de lecture d'un snapshot perime.
  ETAGE 2 (offline, port) -- rejoue la meme resolution que `collect_triggered_abilities` :
      `ABILITY_TRIGGERS` contient-il la cle, et le porteur historique la nomme-t-il encore ?
  ETAGE 3 (live) -- monte un runner avec le porteur historique et lit son kit REEL tel que le
      jeu le resout (`decisionView`), puis dresse la liste des ability-triggers que le port
      instancie effectivement pour lui. C'est la confirmation live du decompile.
  ETAGE 4 (offline, campagne) -- generalise : combien d'entrees de `ABILITY_TRIGGERS` sont
      devenues ORPHELINES (plus aucun porteur) ? `MartialApotheosis` est-elle un cas isole ou
      la premiere d'une serie ? Repond par un COMPTE, ne corrige rien.

RAPPEL DE DOCTRINE (`unit_map.py find --ability`) : un zero de recensement ne prouve pas la
mort d'une ability -- quatre voies (trait, live-event, summon, tile) echappent au gameconfig.
Ce probe rend donc un COMPTE par voie, jamais un verdict binaire ; l'etage 3 le confronte au
jeu qui tourne, et la voie TRAIT est tranchee AU DECOMPILE (hors de portee d'un script Python,
qui ne lit pas le binaire) :

    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility`
    n'est qu'un `TryGetValue` sur le dictionnaire statique bati par
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`.
    Ce cctor enumere 41 paires trait -> TriggeredAbilityType, et la valeur `0x415` (1045,
    MartialApotheosis) N'Y FIGURE PAS -- la suite des valeurs saute de `0x414` a `0x41b`.
    Aucun trait n'accorde donc cette ability. (Mesure du 2026-07-31, build `rnca9r7q6c`.)

Les deux voies restantes (live-event `Enhancement*`, tile `PowerUp_*`) n'accordent aucune
ability de kit d'unite : `MartialApotheosis` ne porte ni l'un ni l'autre de ces prefixes.

PIEGE D'ENUM, a ne pas confondre (deux abilities de noms voisins, DEUX enums differents) :
    `MartialApotheosis`  = PassiveAbilityType/TriggeredAbilityType **1045**  <- CE probe
    `MartialInspiration` = ActiveAbilityType **1191**                        <- une AUTRE
    `GetEmRuntz`         = ActiveAbilityType **1045** (meme id, autre enum)

Usage : python probe_354_martial_apotheosis_carrier.py [--no-live]
ASCII only (console cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
ABILITY = "MartialApotheosis"
CARRIER = "necroOverlord"          # porteur historique (RE case-220, build gqfc5mff6c)
ENEMIES = "necroWarden,eldarRanger,eldarAutarch"
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_probe354_ma_carrier.json"      # SORTIE -> logs/ (#349)

VOIES = ("passiveAbilities", "activeAbilities", "relicAbilities", "mythicAbilities")
SECTIONS = ("lineup", "npc", "summons")


def _snapshots() -> list[Path]:
    """Tous les instantanes de gameconfig presents (pas seulement l'actif), tries du plus
    ancien au plus recent -- cf. `gameconfig._find_gameconfig`, qui ne retient que le dernier
    ECRIT. Comparer les instantanes distingue un changement de CONTENU DU JEU d'un artefact
    de selection de fichier."""
    base = Path.home() / "AppData" / "LocalLow" / "Snowprint"
    return sorted(base.glob("*/gameconfig/*.json"), key=lambda p: p.stat().st_mtime)


def etage1() -> dict:
    """Porteurs de l'ability par (instantane, section, voie). Rend le compte du DERNIER
    instantane (celui que `gameconfig` lit)."""
    print("=== ETAGE 1 -- attribution dans le gameconfig (toutes sections, toutes voies) ===")
    last: dict = {}
    for p in _snapshots():
        try:
            units = (json.loads(p.read_text(encoding="utf-8"))
                     .get("clientGameConfig", {}).get("units", {}))
        except Exception as exc:                       # instantane partiel / illisible
            print("  %s : ILLISIBLE (%s)" % (p.name, exc))
            continue
        hits: dict = {}
        for sec in SECTIONS:
            for uid, u in (units.get(sec) or {}).items():
                if not isinstance(u, dict):
                    continue
                for voie in VOIES:
                    if ABILITY in (u.get(voie) or []):
                        hits.setdefault(voie, []).append("%s/%s" % (sec, uid))
        carrier = (units.get("lineup") or {}).get(CARRIER) or {}
        print("  %s" % p.name)
        print("     porteurs de %s : %s" % (ABILITY, hits or "AUCUN (0 sur les 4 voies)"))
        print("     kit de %s : passives=%s actives=%s"
              % (CARRIER, carrier.get("passiveAbilities"), carrier.get("activeAbilities")))
        last = hits
    return last


def etage2() -> None:
    """Resolution du PORT, a l'identique de `collect_triggered_abilities` : la cle est-elle au
    registre, et le porteur historique la nomme-t-il encore ?"""
    print("=== ETAGE 2 -- resolution du port (mirror de collect_triggered_abilities) ===")
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    classes = ABILITY_TRIGGERS.get(ABILITY, ())
    print("  ABILITY_TRIGGERS[%s] = %s" % (ABILITY, [c.__name__ for c in classes] or "ABSENT"))
    gu = GC.unit(CARRIER) or {}
    passives = gu.get("passiveAbilities") or []
    print("  gameconfig.unit(%s).passiveAbilities = %s" % (CARRIER, passives))
    print("  -> le port instancie %s pour %s : %s"
          % (ABILITY, CARRIER, "OUI" if (classes and ABILITY in passives) else "NON"))
    cfg = GC.ability(ABILITY)
    print("  gameconfig.ability(%s) = %s" % (ABILITY, "PRESENTE " + json.dumps(
        {k: v for k, v in (cfg or {}).items() if k in ("attackRangeType", "constants")})
        if cfg else "ABSENTE"))
    print("     (config d'ability presente + 0 porteur = ability RETIREE DE SON PORTEUR,")
    print("      pas ability supprimee du jeu)")


def _sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return json.loads(r.read())["session"]["id"]


def _rpc(sid: int, method: str, body: dict, timeout: int = 90):
    payload = json.dumps({"method": method, "args": [body]}).encode()
    req = urllib.request.Request(HOST + "/api/scripts/%d/rpc" % sid, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def etage3() -> int:
    """Kit REEL du porteur tel que le JEU le resout, et ability-triggers que le port
    instancie pour lui. Monte son propre runner et le dispose."""
    print("=== ETAGE 3 -- kit LIVE du porteur (le jeu qui tourne tranche) ===")
    sid = _sid()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "4321", "--state-file", str(STATE),
         "--board", "MC1_67", "--p-units", ENEMIES, "--a-units", CARRIER,
         "--hp-player", "500000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("  build runner KO : %s" % ((proc.stderr or proc.stdout or "")[-300:]))
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    print("  runner %s" % rid)
    try:
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ov = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        if ov is None:
            print("  %s absent du build -- etage non mesure" % CARRIER)
            return 1
        # Le kit tel que le JEU l'expose pour CETTE unite (noms d'abilities cotees decision).
        keys = [k for k in ("abilities", "activeAbilities", "passiveAbilities", "traits")
                if k in ov]
        for k in keys:
            print("  live %s.%s = %s" % (CARRIER, k, ov.get(k)))
        # Ce que le PORT instancie pour lui, via le meme chemin que le dispatch.
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        state = load_state(dv, ob, snap, board=board)
        from engine.runner.components import UnitComponent
        oid = next((uid for uid, e in state.entities.items()
                    if (uc := e.get_component(UnitComponent)) is not None
                    and uc.visual_id == CARRIER), None)
        ported = [type(t).__name__ for t in collect_triggered_abilities(state)
                  if getattr(t, "owner_id", None) == oid]
        print("  ability-triggers instancies par le PORT pour %s : %s"
              % (CARRIER, ported or "AUCUN"))
        print("  -> %s dans cette liste : %s"
              % (ABILITY, "OUI" if any("MartialApotheosis" in n for n in ported) else "NON"))
        return 0
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            print("  runner %s dispose" % rid)
        except Exception as exc:
            print("  disposeRunner KO : %s" % exc)


def etage4() -> None:
    """GENERALISATION -- `MartialApotheosis` est-elle un cas isole ? Compte les entrees de
    `ABILITY_TRIGGERS` (registre des ability-triggers, cle = NOM d'ability de gameconfig) dont
    plus AUCUNE unite ne porte la cle, sur les trois sections. Une entree orpheline n'est pas
    un bug de port : c'est un port devenu INERTE parce que le jeu a retire l'ability de ses
    porteurs. Ce compte dit si le rouge #354 est un incident isole ou le premier d'une serie
    ouverte par la mise a jour du build."""
    print("=== ETAGE 4 -- entrees de registre devenues ORPHELINES (generalisation) ===")
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    snaps = _snapshots()
    if not snaps:
        print("  aucun instantane de gameconfig -- etage non mesure")
        return
    units = (json.loads(snaps[-1].read_text(encoding="utf-8"))
             .get("clientGameConfig", {}).get("units", {}))
    porte: dict = {}
    for sec in SECTIONS:
        for uid, u in (units.get(sec) or {}).items():
            if not isinstance(u, dict):
                continue
            for voie in VOIES:
                for name in (u.get(voie) or []):
                    porte.setdefault(name, []).append("%s/%s" % (sec, uid))
    orphelines = sorted(k for k in ABILITY_TRIGGERS if k not in porte)
    print("  ABILITY_TRIGGERS : %d entrees" % len(ABILITY_TRIGGERS))
    print("  ORPHELINES (0 porteur, toutes sections/voies) : %d" % len(orphelines))
    for k in orphelines:
        cfg = GC.ability(k)
        print("     %-26s config d'ability : %s" % (k, "PRESENTE" if cfg else "ABSENTE"))
    if not orphelines:
        print("     (aucune -- toutes les cles du registre ont au moins un porteur)")


def main() -> int:
    hits = etage1()
    print("")
    etage2()
    print("")
    rc = 0 if "--no-live" in sys.argv else etage3()
    print("")
    etage4()
    print("")
    print("=== VERDICT ===")
    print("  porteurs de %s dans l'instantane ACTIF : %s" % (ABILITY, hits or "AUCUN"))
    print("  Un port fidele ne peut PAS dispatcher une ability que le gameconfig n'accorde")
    print("  a personne : l'etage qui decroche est l'ATTRIBUTION, pas le rail turn-start.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
