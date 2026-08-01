"""#448-r1 -- `StormboyzStrike_FallbackAbility`, `StormboyzStrike_MissAbility` et l'effet
`1179 StormboyzStrike_AlreadyUsedTile` : QUI le pose, QUI le LIT, et pour quoi.

Residu nomme en §7 de `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`.

Le probe a deux volets, et le premier suffit a trancher l'item 3 SANS session live :

VOLET A -- OFFLINE, re-derive integralement
  A1. Recensement EXHAUSTIF des porteurs de l'immediat `0x49b` dans GameAssembly.dll, par
      DESASSEMBLAGE capstone lineaire de chacune des fonctions de
      `data/symbols/<build>/ghidra/functions.tsv` -- PAS par recherche d'octets.
      ⚠ La recherche d'octets + heuristique d'opcode RATE la forme `mov dword [rbp+disp32], imm32`,
      et c'est exactement sous cette forme qu'est ecrit l'enregistrement de 0x49b dans
      `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` : mesure faite le 2026-08-01,
      l'heuristique concluait « 1179 n'est pas enregistre », ce qui est FAUX.
  A2. Le poids IA lu par NOM. C'est LA reponse a « qui lit 1179 » : aucun lecteur ne charge
      l'immediat, le lecteur passe par `Enum.ToString(effectType)` ->
      `BC.Utilities.<profil>.TileEffects[<nom>]`.
  A3. Contre-epreuve du MULTIPLICATEUR : `TileEffectsUtility` ne multiplie un poids par
      `GetStatusEffectMultiplier` que si `StaticBattleRules.Effect$$IsTileStatusEffect(type)`.
      Cet `OrderedSet` est peuple par immediats dans le `.cctor` -> A1 prouve que 1179 n'y est pas.
  A4. Fermeture : aucune classe d'effet dediee dans `classes.tsv` (le builder construit un
      `NoneEffect`), donc AUCUNE contribution a un canal de COMBAT.

VOLET B -- LIVE (`--live`), confronte la RE
  Greffe du passif `StormboyzStrike` sur une unite du pool (`case-92` §5bis, recours 3 -- le seul
  porteur `orksNpc6Stormboy` est npc et n'a aucun summoner). La greffe monte les TROIS triggered
  d'un coup : `AbilitiesDatabase.<>c$$<InitializeTriggeredAbilities>b__28_134`, l'UNIQUE entree
  pour `TriggeredAbilityType.StormboyzStrike = 0x475`, construit une `List` de TROIS instances.
  B1. Le porteur part hors plateau sous `1140` (acquis #366-r1 tranche 3/3).
  B2. On termine son tour SANS le bouger -> `On(0x28 = UnitFinishedTurn)` -> le Fallback le repose
      sur une tuile et MARQUE cette tuile avec `1179`, `turns: 1`.
  B3. La tuile marquee est EXACTEMENT celle ou il a atterri (discriminant de la pose).

Reproduction :
    python probe_448_r1_stormboyz_fallback_miss.py            # volet A seul (offline, ~40 s)
    python probe_448_r1_stormboyz_fallback_miss.py --live     # A + B (monte UN runner)
"""
from __future__ import annotations

import argparse
import bisect
import json
import struct
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                   # noqa: E402

ABILITY = "StormboyzStrike"
TELEPORTING_IN = 0x474            # 1140 EffectType.StormboyzStrike_TeleportingIn
ALREADY_USED_TILE = 0x49B         # 1179 EffectType.StormboyzStrike_AlreadyUsedTile
IMAGE_BASE = 0x180000000

#: Les 6 porteurs de 0x49b QUI NE SONT PAS le poseur -- tous des HOMONYMES d'autres tables d'enum
#: (`ActiveAbilityType.CultDemagogue` = 1179, `TriggeredAbilityType.PsychicStalk` = 1179), plus
#: l'enregistrement de l'effet lui-meme. Aucun n'est un LECTEUR de l'EffectType 1179.
EXPECTED_IMM_SITES = {
    "IdunBattle.AI.Playbook.Loki.CultDemagoguePlaybook$$.ctor":
        "ActiveAbilityType.CultDemagogue (homonyme)",
    "IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders":
        "ActiveAbilityType.CultDemagogue (homonyme) -- enregistrement du playbook",
    "IdunBattle.Core.Services.AbilitiesDatabase$$InitializeActiveAbilities":
        "ActiveAbilityType.CultDemagogue (homonyme)",
    "IdunBattle.Core.Services.AbilitiesDatabase$$InitializeTriggeredAbilities":
        "TriggeredAbilityType.PsychicStalk (homonyme)",
    "IdunBattle.Entities.Effects.Loki.PsychicStalk_VisualEffectEffect$$.ctor":
        "TriggeredAbilityType.PsychicStalk (homonyme)",
    "IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects":
        "EffectType 1179 -- ENREGISTREMENT (builder b__14_197 -> NoneEffect)",
}
POSER = "IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility$$CreateBehaviour"

#: `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor` peuple par
#: immediats l'`OrderedSet` que lit `$$IsTileStatusEffect` : {Fire, Ice, Darkness, Contaminated,
#: DespoiledGround}. LU au desassemblage (5 `OrderedSet.Add` consecutifs).
TILE_STATUS_EFFECTS = {5, 0x11, 0x3A, 0x4DC, 0x5C4}


# ---------------------------------------------------------------- VOLET A (offline)
def _build_hash() -> str:
    d = sorted(p.name for p in (ROOT / "data" / "symbols").iterdir()
               if p.is_dir() and (p / "ghidra" / "functions.tsv").exists())
    if not d:
        raise SystemExit("aucune table de symboles sous data/symbols/")
    return d[-1] if len(d) == 1 else sorted(d, key=lambda h: (ROOT / "data" / "symbols" / h
                                                              / "ghidra" / "functions.tsv")
                                            .stat().st_mtime)[-1]


def _dll_path(build: str) -> Path:
    return Path.home() / "AppData" / "Local" / "tacticus" / "games" / build / "GameAssembly.dll"


def _sections(buf: bytes):
    pe = struct.unpack_from("<I", buf, 0x3C)[0]
    coff = pe + 4
    n = struct.unpack_from("<H", buf, coff + 2)[0]
    opt = struct.unpack_from("<H", buf, coff + 16)[0]
    base = coff + 20 + opt
    out = []
    for i in range(n):
        o = base + i * 40
        out.append(dict(vaddr=struct.unpack_from("<I", buf, o + 12)[0],
                        vsize=struct.unpack_from("<I", buf, o + 8)[0],
                        raw=struct.unpack_from("<I", buf, o + 20)[0],
                        chars=struct.unpack_from("<I", buf, o + 36)[0]))
    return [s for s in out if s["chars"] & 0x20000000]


def scan_immediate(value: int, build: str) -> dict:
    """Toutes les instructions du binaire qui chargent `value` comme IMMEDIAT, par fonction.

    Desassemblage capstone LINEAIRE de chaque plage [addr(i), addr(i+1)) de `functions.tsv`.
    Rend {symbole: [(offset, texte), ...]}. Leve si capstone manque (pas de repli heuristique :
    un repli qui rate une forme d'encodage rend un ZERO qui se lit comme une preuve).
    """
    import capstone

    dll = _dll_path(build)
    if not dll.exists():
        raise SystemExit("GameAssembly.dll introuvable pour le build %s : %s" % (build, dll))
    buf = dll.read_bytes()
    secs = _sections(buf)

    def to_off(va):
        rva = va - IMAGE_BASE
        for s in secs:
            if s["vaddr"] <= rva < s["vaddr"] + s["vsize"]:
                return s["raw"] + (rva - s["vaddr"])
        return None

    rows = []
    tsv = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    for line in tsv.open("r", encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2:
            try:
                rows.append((int(p[0], 16), p[1]))
            except ValueError:
                pass
    rows.sort()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits: dict = {}
    for i, (va, name) in enumerate(rows):
        off = to_off(va)
        if off is None:
            continue
        end = rows[i + 1][0] if i + 1 < len(rows) else va + 0x400
        size = min(end - va, 0x20000)
        if size <= 0:
            continue
        for ins in md.disasm(buf[off:off + size], va):
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_IMM and op.imm == value:
                    hits.setdefault(name, []).append(
                        (ins.address - va, "%s %s" % (ins.mnemonic, ins.op_str)))
    return hits


def volet_a(build: str) -> dict:
    print("== VOLET A (offline) -- build %s ==" % build)

    print("\n-- A1. porteurs de l'immediat 0x%x, desassemblage EXHAUSTIF --" % ALREADY_USED_TILE)
    hits = scan_immediate(ALREADY_USED_TILE, build)
    total = sum(len(v) for v in hits.values())
    print("   %d instructions dans %d fonctions" % (total, len(hits)))
    unknown = []
    for name in sorted(hits):
        role = EXPECTED_IMM_SITES.get(name)
        if name == POSER:
            role = "POSEUR -- AddEffect(0x49b, stateRef, <la tuile choisie>, turns: 1)"
        if role is None:
            unknown.append(name)
        print("   %-95s %s" % (name[:95], role or "?? NON ATTENDU"))
    readers = [n for n in hits if n != POSER and n not in EXPECTED_IMM_SITES]
    print("   -> lecteurs de l'EffectType 1179 par IMMEDIAT : %d" % len(readers))
    if unknown:
        print("   !! sites non attendus (la carte a change, RE a refaire) : %s" % unknown)

    print("\n-- A2. le LECTEUR, par NOM : le poids IA de la categorie TileEffects --")
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    found = {}
    for profile, cats in (bc.get("Utilities") or {}).items():
        cat = (cats or {}).get("TileEffects") or {}
        if "StormboyzStrike_AlreadyUsedTile" in cat:
            found[profile] = cat["StormboyzStrike_AlreadyUsedTile"]
        rank = sorted(cat.items(), key=lambda kv: kv[1])
        if rank:
            print("   profil %-20s %d cles ; le plus NEGATIF = %s (%s)"
                  % (profile, len(cat), rank[0][0], rank[0][1]))
    print("   BC.Utilities[*].TileEffects['StormboyzStrike_AlreadyUsedTile'] = %s" % found)

    print("\n-- A3. le multiplicateur de duree NE s'applique PAS a 1179 --")
    print("   IsTileStatusEffect = OrderedSet%s (peuple par immediats dans "
          "StaticBattleRules.Effect$$.cctor)" % sorted(TILE_STATUS_EFFECTS))
    print("   1179 dedans ? %s -> poids BRUT, le port est EXACT"
          % (ALREADY_USED_TILE in TILE_STATUS_EFFECTS))

    print("\n-- A4. aucune classe d'effet dediee (builder -> NoneEffect) --")
    n = 0
    for p in (ROOT / "data" / "symbols" / build / "frida" / "classes.tsv").open(
            "r", encoding="utf-8", errors="replace"):
        if "AlreadyUsedTile" in p:
            n += 1
            print("   %s" % p.strip())
    print("   classes '*AlreadyUsedTile*' dans classes.tsv : %d" % n)

    print("\n-- A5. le port LIT-il ce poids ? --")
    from engine.utilities.tile import TileEffectsUtility
    wt = _weights_from_bc(bc)
    u = TileEffectsUtility().evaluate(
        None, {"effects": ["StormboyzStrike_AlreadyUsedTile"]}, None, wt)
    print("   TileEffectsUtility.evaluate(meta.effects=['StormboyzStrike_AlreadyUsedTile']) = %s"
          % u)
    return {"imm_sites": {k: v for k, v in hits.items()}, "readers": readers,
            "weight": found, "port_utility": u, "carriers": _carriers()}


def _weights_from_bc(bc):
    from engine.weights import Weights
    return Weights(bc.get("Utilities") or {})


def _carriers() -> list:
    idx = GC._index()
    out = []
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            names = list(u.get("passiveAbilities") or []) + list(u.get("activeAbilities") or [])
            if ABILITY in names:
                out.append({"id": uid, "bucket": bucket, "traits": u.get("traits")})
    return out


# ---------------------------------------------------------------- VOLET B (live)
def volet_b(board: str, seed: int, graft: str, foes: list) -> dict:
    import catalog_inject as CI
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=120):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}

    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state_file = logs / "p448r1_state.json"
    bc_path = logs / "p448r1_bc.json"

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    rep = CI.graft_passive_ability(bc, graft, ABILITY)
    bc_path.write_text(json.dumps(bc), encoding="utf-8")
    print("== VOLET B (live) -- greffe %s sur %s : %s" % (ABILITY, graft, rep))

    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", graft, "--a-units", ",".join(foes), "--no-ai",
           "--seed-bc", str(bc_path), "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-2000:])
        sys.stdout.write((p.stderr or "")[-2000:])
        raise SystemExit("build KO")
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    sid = _resolve_session()
    print("   runner %s (session %s)" % (rid, sid))
    out = {"runner": rid, "graft": graft, "board": board, "seed": seed}
    try:
        def snapshot(tag):
            # ⚠ Le porteur est HORS PLATEAU sous 1140 (acquis #366-r1) : `observeBattle.units[]`
            # NE LE LISTE PAS (mesure du 2026-08-01 -- il n'y figure ni vivant ni mort). Le seul
            # canal qui le rend est `decisionView`, avec `pos: null`.
            ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                           "allAbilities": True}, 150)
            # `includeInactive: true` -- `readEffectsByTile` filtre par defaut `!active`, et
            # `1179` est construit par un `NoneEffect` : sans cette option, un effet pose mais
            # INACTIF serait invisible et se lirait a tort comme « jamais pose ».
            tm = rpc(sid, "tileMeta", {"runnerId": rid, "includeInactive": True}, 90)
            tiles = tm.get("tiles") if isinstance(tm, dict) else None
            if tiles is None and isinstance(tm, list):
                tiles = tm
            marked, teleporting = [], []
            for t in (tiles or []):
                for e in (t.get("effects") or []):
                    et = int(e.get("effectType") or -1)
                    row = {"col": t.get("col"), "row": t.get("row"),
                           "remaining": e.get("remaining"), "name": e.get("name")}
                    if et == ALREADY_USED_TILE:
                        marked.append(row)
                    elif et == TELEPORTING_IN:
                        teleporting.append(row)
            # IDENTIFICATION DU PORTEUR -- mesure du 2026-08-01, a garder telle quelle : tant qu'il
            # est HORS PLATEAU sous 1140, le porteur greffe sort de `decisionView` avec
            # `visualId = null`, `team = null` ET `pos = null` (et il est totalement ABSENT
            # d'`observeBattle.units[]`). On ne peut donc PAS le retrouver par son visualId au
            # premier etat lisible : on le reconnait a `pos is None`, et on MEMORISE son id.
            me = None
            for u in (dv.get("units") or []):
                if out.get("uid") is not None and u.get("id") == out["uid"]:
                    me = u
                    break
                if (u.get("visualId") or u.get("unitId")) == graft:
                    me = u
                    break
            if me is None:
                cand = [u for u in (dv.get("units") or []) if u.get("pos") is None]
                if len(cand) == 1:
                    me = cand[0]
                    print("        (porteur identifie par pos=None : id=%s, visualId=%s)"
                          % (me.get("id"), me.get("visualId")))
                else:
                    print("        !! porteur introuvable ; decisionView units=%s"
                          % [{k: v for k, v in (u or {}).items()
                              if k in ("id", "visualId", "unitId", "team", "pos")}
                             for u in (dv.get("units") or [])][:8])
            in_ob = [u.get("visualId") for u in (ob.get("units") or [])]
            print("   [%s] porteur(decisionView)=%s" % (tag, {k: (me or {}).get(k) for k in
                                                              ("id", "visualId", "pos", "alive",
                                                               "hasAction")}))
            print("        effets porteur=%s" % ((me or {}).get("effects"),))
            print("        observeBattle.units=%s | tileMeta: %d tuiles"
                  % (in_ob, len(tiles or [])))
            print("        tuiles marquees 1179=%s | 1140 sur tuile=%s" % (marked, teleporting))
            any_eff = [{"col": t.get("col"), "row": t.get("row"),
                        "eff": [(e.get("effectType"), e.get("name"), e.get("remaining"))
                                for e in (t.get("effects") or [])]}
                       for t in (tiles or []) if t.get("effects")]
            print("        TOUTES les tuiles a effet (canal tileMeta) : %s" % (any_eff or "AUCUNE"))
            # DISCRIMINANT INDEPENDANT DU CANAL TUILE : le NOMBRE d'entites `EntityType.Effect`
            # (=3). Un `AddEffect` reussi CREE une entite, que `tileMeta` la publie ou non. Si ce
            # compte ne bouge pas, l'effet n'a pas ete pose ; s'il bouge sans que `tileMeta` le
            # montre, c'est le CANAL qui est aveugle -- deux verdicts opposes qu'aucune lecture
            # de `tileMeta` seule ne peut separer.
            n_eff = (ob.get("byType") or {}).get("3")
            if n_eff is None:
                n_eff = (ob.get("byType") or {}).get(3)
            print("        entites EntityType.Effect (byType[3]) = %s | counts=%s"
                  % (n_eff, ob.get("counts")))
            return {"marked": marked, "me": me, "tiles_n": len(tiles or []), "in_ob": in_ob,
                    "any_eff": any_eff, "n_eff": n_eff}

        out["b1"] = snapshot("B1 avant")
        if out["b1"]["me"]:
            out["uid"] = out["b1"]["me"].get("id")
        uid = out.get("uid")
        print("   -> applyAction finish sur le porteur %s (emet On(0x28 UnitFinishedTurn))" % uid)
        fin = rpc(sid, "applyAction",
                  {"runnerId": rid, "action": {"kind": "finish", "unitId": uid}}, 120)
        out["finish"] = {k: fin.get(k) for k in ("mutated", "error") if k in fin}
        print("      applyAction -> %s" % out["finish"])
        out["b2"] = snapshot("B2 apres finish")

        # B3 -- SEPARER « la tuile ne possede pas l'effet » de « le capteur le filtre ».
        # `readEffectsByTile` (frida/hooks/game/effects.ts) itere les entites Tile, lit leur
        # `EffectsOwnedComponent` et JETTE tout ce qui est `removed` (meme sous includeInactive).
        # `dumpEntityComponents` est read-only et ne filtre rien : c'est le seul arbitre.
        landed = ((out["b2"].get("me") or {}).get("pos")) or {}
        # ⚠ `tileMeta` ne publie PAS d'id d'entite (cles : col/row/elevation/isWall/isTemporary/
        # isTerritory/effects). C'est `boardGraph` qui porte l'id, et son `t.id` EST l'entityId
        # de la tuile (meme convention que `TileEffectTrigger.owner_id`).
        tile_entity = None
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        for t in (bg.get("tiles") or []):
            if t.get("col") == landed.get("col") and t.get("row") == landed.get("row"):
                tile_entity = t.get("id")
                print("   B3 tuile d'atterrissage (%s,%s) -> entite %s"
                      % (landed.get("col"), landed.get("row"), tile_entity))
                break
        if tile_entity is not None:
            dmp = rpc(sid, "dumpEntityComponents",
                      {"runnerId": rid, "entityId": tile_entity, "withFields": True}, 90)
            comps = [c.get("cls") for c in (dmp.get("components") or [])]
            out["b3"] = {"tile_entity": tile_entity, "components": comps}
            print("      composants de l'entite-tuile : %s" % comps)
            print("      NB: `dumpEntityComponents` rend la STRUCTURE (noms/offsets de champs), PAS")
            print("        les VALEURS : il ne peut pas lister le contenu de")
            print("        `EffectsOwnedComponent.ActiveEffectIds`. Trancher \"la tuile ne possede")
            print("        pas l'effet\" de \"le capteur le filtre\" demande un capteur NEUF ->")
            print("        cf. docs/rl/case-448-r1-stormboyz-fallback-miss.md sec.4 (ancrage).")
        else:
            print("   B3 : entite-tuile non identifiable")

        d = None
        if out["b1"].get("n_eff") is not None and out["b2"].get("n_eff") is not None:
            d = out["b2"]["n_eff"] - out["b1"]["n_eff"]
        print("\n   == BILAN VOLET B ==")
        print("   pos porteur    : %s -> %s" % ((out["b1"].get("me") or {}).get("pos"),
                                                (out["b2"].get("me") or {}).get("pos")))
        print("   effet 1140     : present -> %s"
              % ("absent" if not any(e.get("effectType") == TELEPORTING_IN
                                     for e in ((out["b2"].get("me") or {}).get("effects") or []))
                 else "TOUJOURS LA"))
        print("   entites Effect : %s -> %s (delta %s)"
              % (out["b1"].get("n_eff"), out["b2"].get("n_eff"), d))
        print("   1179 sur tileMeta (includeInactive=true) : %s"
              % (out["b2"].get("marked") or "AUCUNE"))
        print("   tuiles a effet identiques avant/apres ? %s"
              % (out["b1"].get("any_eff") == out["b2"].get("any_eff")))
        out["delta_effect_entities"] = d
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            print("   runner %s dispose" % rid)
        except Exception as exc:                                        # noqa: BLE001
            print("   dispose KO: %s" % exc)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="joue aussi le volet B (monte 1 runner)")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--graft", default="orksNob")
    ap.add_argument("--foes", default="ultraTitus")
    a = ap.parse_args()
    build = _build_hash()
    res = volet_a(build)
    print("\n   porteurs gameconfig de %s : %s" % (ABILITY, res["carriers"]))
    if a.live:
        print()
        volet_b(a.board, a.seed, a.graft, a.foes.split(","))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
