"""#366-r1 tranche 1 -- ActiveAbilityType 1023 `Burrowers` : CONFRONTATION live port <-> natif.

RE (decompile = verite, cf. `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §5) :

  * `IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` = TROIS
    `AActiveAbility$$Execute` successifs -- `RemoveUnitFromItsTiles(Caster, true)` &
    `RemoveAllForcedAttackTargets(Caster)` & `AddEffect(0x410 Burrowers_Hidden, stateRef,
    targets: Caster, turns: null)`. L'etage 3 est un `AddEffect` SANS selecteur SOURCE (surcharge
    5 arguments d'`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`), donc l'effet vit sur le
    CASTER -- pas un `AddBondEffect` sur une tuile comme 1011.
  * `...BurrowersAbility$$.ctor` ne passe par AUCUN ctor de `TargetingOptions` : il recopie le
    preset statique `<TargetingOptions statics>+0x280` (`isSelfCasting = 1`, range =
    `TargetingRange statics+0x60` = RANGE_SELF, forceMeleeTarget = 1, `rules = 0x8004`) puis
    `AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`.
  * `...BurrowersAbility$$GetDynamicInvalidCasterReason` (armee par le bit
    `CasterMatchesDynamicRule` 0x4) rend le litteral **4** quand `casterTiles` est VIDE, ou quand
    l'une des tuiles du caster est `IdunBattle.Entities.TileExtensions$$IsTemporary` ; 0 sinon.
  * Duree : `idun...StaticBattleRules.Effect$$DefaultAmountOfRounds` ne connait pas 0x410 (branche
    `0x3a < t < 0x42a`, `t != 0x4f`, `t != 0x429` -> Nullable null) -> effet PERMANENT
    (`remaining = 0`). Retrait explicite par le `RemoveEffect(Owner, Nullable(0x410))` de
    `...BurrowersAbility_Appear$$ExecuteBehaviour` (1024, HORS perimetre).

MONTAGE. `unit_map.py find --ability Burrowers` rend 6 unites : le SUMMON `tyranSmnRipperSwarm` et
cinq NPC `tyranNpc2RipperSwarm*`. Un summon s'OBSERVE mais ne se COMMANDE pas (#291) -> recours 3 de
`docs/rl/case-92-catalog-injection.md` §5bis : GREFFE de 1023 sur des heros DU POOL, dans une COPIE
du seed BC (jamais le seed partage). Legitime : `gameconfig.ability("Burrowers")` n'a AUCUNE variable
ni constante, et le behaviour ne lit ni stat, ni trait, ni arme du caster -- seulement ses TUILES.

CE QUE LE PROBE MESURE, sur DEUX couples (board, seed) :

  CONFRONT -- le MEME cast joue OFFLINE (voie complete `Runner.apply(ActiveAbilityMessage)`) sur
              l'etat capture JUSTE AVANT, puis LIVE ; les deux etats finaux compares TERME A TERME
              (`pos`, `feet`, `alive`, effet 1040 porte par le caster).
  E-SWAP   -- la MATRICE 2x2 {1023, 1024} x {enfoui, temoin} des `casterReason` natifs : elle est
              CROISEE (0x1 / 0 / 0 / 0x1). Le natif REMPLACE 1023 par 1024 sur le caster pendant
              l'enfouissement -- couche `ActiveAbilityComponent` NON portee, residu nomme.
  E-GATE   -- DISCRIMINANT DE VERDICT, apres un TOUR COMPLET (anti-confond « action consommee ») :
              natif et port REFUSENT tous deux un second 1023 sur l'unite ENFOUIE, et ACCEPTENT tous
              deux sur le TEMOIN -- mais a des ETAGES differents (natif : `AttackQuery`, echange
              d'ability ; port : clause TUILE-NULLE `AllowNullCasterTile`). Cette clause generique
              etait ABSENTE du port : sans elle il ACCEPTAIT le second cast, et il l'acceptait DEJA
              pour 1011 depuis #438 -- regression permissive fermee par cette meme tranche.

Usage (depuis scripts/python) :
    python probe_366_r1_burrowers.py [--keep]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe366r1burrow"
STATE = LOGS / "state_366_r1_burrowers.json"      # SORTIE -> logs/ (#349), JAMAIS data/
SEED_BC = LOGS / "seed_bc_366_r1_burrowers.json"  # copie greffee, JAMAIS le seed BC partage

BURROWERS = 1023          # ActiveAbilityType.Burrowers
APPEAR = 1024             # ActiveAbilityType.Burrowers_Appear
HIDDEN = 1040             # EffectType.Burrowers_Hidden (0x410)
GRAFT_A = "tyranParasite"
GRAFT_B = "tyranNeurothrope"
P_UNITS = GRAFT_A + "," + GRAFT_B
A_UNITS = "ultraTitus,ultraInceptorSgt"

# DEUX couples (board, seed) -- la confrontation doit tenir sur les deux, pas sur un montage unique.
COUPLES = [("MC1_67", "777"), ("C3_26", "31337")]


# --------------------------------------------------------------------------- transport

def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result")


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


# --------------------------------------------------------------------------- montage

def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities = [1023]` sur les DEUX greffons."""
    bc = L._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") in (GRAFT_A, GRAFT_B):
            u["ActiveAbilities"] = [BURROWERS]
            n += 1
    if n != 2:
        raise SystemExit("MONTAGE INVALIDE : %d entree(s) greffee(s) au lieu de 2" % n)
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[burrow] greffe ActiveAbilities=[%d] sur %s et %s" % (BURROWERS, GRAFT_A, GRAFT_B))


def build(seed_value: str, board_id: str) -> int:
    write_graft_seed_bc()
    if STATE.exists():
        STATE.unlink()
    p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17",
               "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
               "--state-file", str(STATE)])
    if not STATE.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure): "
                         + (p.stderr or p.stdout or "")[-800:])
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- lectures

def units_by_vid(rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 90)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = {"vid": u.get("visualId"), "ctrl": u.get("ctrl"),
                            "pos": (p.get("col"), p.get("row")), "alive": u.get("alive"),
                            "hasAction": u.get("hasAction")}
    return out


def capture(rid) -> dict:
    """Les CINQ canaux dont `load_state` a besoin pour materialiser l'etat offline."""
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                        "includeInactive": True}, 90),
            "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "tm": rpc("tileMeta", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def offline_view(st, uid: int) -> dict:
    """Ce que l'ETAT PORTE dit de l'unite `uid` -- la forme EXACTE des deux cotes, pour que la
    comparaison soit terme a terme. `hidden` = les instances NON consommees de 1040 PORTEES PAR LE
    CASTER (l'effet de `Burrowers` vit sur l'unite, pas sur une tuile : c'est LA difference d'avec
    1011, dont le marqueur allait sur la tuile visee)."""
    from engine.runner.components import UnitComponent, get_unit_feet
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    feet = get_unit_feet(st, int(uid))
    hidden = sorted((int(getattr(x, "effect_type", -1)), getattr(x, "remaining_turns", None))
                    for x in (st.effects.by_unit.get(int(uid)) or [])
                    if int(getattr(x, "effect_type", -1)) == HIDDEN and not x.consumed)
    return {"pos": (feet[0] if feet else None), "feet": feet,
            "alive": (uc.alive if uc is not None else None), "hidden": hidden}


def ability_reason(rid, caster, ability, target):
    return rpc("abilityReason", {"runnerId": rid, "casterId": caster,
                                 "abilityType": ability, "targetId": target}, 60) or {}


def _reason_hex(r):
    """`abilityReason` rend `{hex, reasons}` (ou None quand la raison est vide)."""
    if not isinstance(r, dict):
        return 0
    v = r.get("hex")
    if isinstance(v, str):
        return int(v, 16)
    return int(v or 0)


# --------------------------------------------------------------------------- etapes

def confront(rid, caster_a, fails) -> dict:
    """LE CRITERE : apres un cast de 1023, le caster est-il encore sur le plateau, et l'etat
    resultant est-il TERME A TERME celui du natif ? -- pose au NATIF et au PORT sur le MEME etat de
    depart. On capture AVANT, on rejoue OFFLINE par la voie COMPLETE (`Runner.apply` : gates de
    ciblage inclus -- un refus se verrait ici), puis on joue LIVE et on RECHARGE."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    pre = capture(rid)
    st, _board = offline_state(pre)
    before = offline_view(st, caster_a)
    # --- PORT : la voie COMPLETE. Cast SELF-CAST -> la cible EST le caster.
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_a), target_id=int(caster_a),
                                      ability_type=BURROWERS))
    last = runner.ability_handler.last or {}
    port = offline_view(st, caster_a)
    # --- NATIF : le meme cast, en live, puis rechargement de l'etat d'apres.
    r = _duel(["act", "ability", "--caster", str(caster_a), "--ability", str(BURROWERS),
               "--target", str(caster_a), "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("CONFRONTATION : cast live REFUSE (montage): %s"
                         % (r.stdout or r.stderr)[-800:])
    st2, _board2 = offline_state(capture(rid))
    native = offline_view(st2, caster_a)

    if last.get("ported") is not True:
        fails.append("CONFRONT: l'ability 1023 n'est pas EXECUTEE cote port (last=%r)" % (last,))
    for k in ("pos", "feet", "alive", "hidden"):
        if port[k] != native[k]:
            fails.append("CONFRONT %s : port=%r != natif=%r" % (k, port[k], native[k]))
    if before["pos"] is None:
        fails.append("CONFRONT: le caster n'avait DEJA pas de position avant le cast -- montage nul")
    if native["pos"] is not None:
        fails.append("CONFRONT: le caster natif garde une position %r apres 1023" % (native["pos"],))
    if native["feet"] != []:
        fails.append("CONFRONT: empreinte native = %r (attendu [])" % (native["feet"],))
    if native["alive"] is not True:
        fails.append("CONFRONT: le caster natif n'est plus vivant -- il est HORS PLATEAU, pas mort")
    if native["hidden"] != [(HIDDEN, None)]:
        fails.append("CONFRONT: effets 1040 cote natif = %r (attendu [(%d, None)] = PERMANENT)"
                     % (native["hidden"], HIDDEN))
    print("[CONFRONT] avant=%r" % (before,))
    print("           port =%r" % (port,))
    print("           natif=%r" % (native,))
    return {"before": before, "port": port, "native": native, "last": last, "state": st2}


def _cross(rid, caster_a, caster_b) -> dict:
    """La MATRICE 2x2 {1023, 1024} x {ENFOUI, TEMOIN} des `casterReason` natifs."""
    return {(a, lbl): _reason_hex(ability_reason(rid, u, a, u).get("casterReason"))
            for a in (BURROWERS, APPEAR)
            for u, lbl in ((caster_a, "enfoui"), (caster_b, "temoin"))}


def e_swap(rid, caster_a, caster_b, fails) -> None:
    """L'ECHANGE D'ABILITY, mesure par la MATRICE 2x2 -- et c'est LE piege de lecture de ce cas.

    `abilityReason` interroge `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason`, un
    etage AU-DESSUS de `TargetingQuery` : il rend `GenericBrokenTargetingRule(1)` (le litteral
    `ValidRequest` re-utilise) des que `ActiveAbilityComponent$$GetOrNull(baseUnit, type)` est NUL,
    que `ActiveAbility$$get_CanCurrentlyBeUsed` est faux, ou que `+0x44 == 0` -- AVANT toute cascade
    de ciblage. La matrice attendue est donc CROISEE :

        1023 sur l'ENFOUI -> 0x1   |  1023 sur le TEMOIN -> 0
        1024 sur l'ENFOUI -> 0     |  1024 sur le TEMOIN -> 0x1

    C'est-a-dire : pendant l'enfouissement le natif REMPLACE 1023 par 1024 sur le caster. Ce
    mecanisme (couche `ActiveAbilityComponent` / disponibilite d'ability) n'est PAS porte -- le port
    n'a aucune couche de disponibilite -- et c'est un RESIDU NOMME de cette tranche.

    ⚠ Corollaire de lecture : cette matrice ne SEPARE PAS l'echange d'ability de la regle
    `HasEffect(caster, 0x410)` de `...BurrowersAbility_Appear$$GetDynamicInvalidCasterReason` (les
    deux predisent la meme matrice, et les deux rendent le litteral 1). La PRESENCE de l'effet, elle,
    est etablie ailleurs et sans ambiguite : par `confront`, des deux cotes
    (`hidden = [(1040, None)]`)."""
    x = _cross(rid, caster_a, caster_b)
    want = {(BURROWERS, "enfoui"): 0x1, (BURROWERS, "temoin"): 0x0,
            (APPEAR, "enfoui"): 0x0, (APPEAR, "temoin"): 0x1}
    for k, v in want.items():
        if x[k] != v:
            fails.append("E-SWAP %s : natif=%s (attendu %s)" % (k, hex(x[k]), hex(v)))
    print("[E-SWAP] 1023 enfoui=%s temoin=%s | 1024 enfoui=%s temoin=%s"
          % (hex(x[(BURROWERS, "enfoui")]), hex(x[(BURROWERS, "temoin")]),
             hex(x[(APPEAR, "enfoui")]), hex(x[(APPEAR, "temoin")])))


def e_gate(rid, caster_a, caster_b, fails) -> None:
    """DISCRIMINANT DE VERDICT, ANTI-CONFONDU par un TOUR COMPLET (`endturn` + `aiturn`).

    Le tour complet ecarte le confond « action deja consommee » : au tour suivant les deux unites ont
    `hasAction = true`, et pourtant la matrice 2x2 est INCHANGEE -- le refus de 1023 sur l'enfoui
    n'est donc PAS la consommation d'action, c'est l'echange d'ability (cf. `e_swap`).

    CE QUI EST COMPARE ICI EST LE **VERDICT** (refus / acceptation), pas le code, et c'est
    volontaire : les deux moteurs refusent le second 1023 sur l'unite enfouie, mais a des ETAGES
    DIFFERENTS, tous deux lus au decompile --

      * NATIF  : `AttackQuery$$GetInvalidCasterReason` -> `0x1` (l'ability 1023 n'est plus celle du
                 caster ; couche NON portee) ;
      * PORT   : `TargetingQuery$$GetInvalidCasterReason` clause TUILE-NULLE ->
                 `AllowNullCasterTile` (0x40000000). Cette clause etait ABSENTE du port avant cette
                 tranche : sans elle le port ACCEPTAIT le second cast, la ou le natif le refuse.
                 Elle est un mirror VERBATIM du natif (`!AllowNullCasterTile && !CasterHasNoTile &&
                 IsNullOrEmpty(casterTiles)`), donc elle ne peut jamais refuser un cast que le natif
                 accepterait -- avec `casterTiles` vide, la cascade native refuse de toute facon.

    Le TEMOIN, toujours sur le plateau, doit etre ACCEPTE des DEUX cotes : c'est lui qui prouve que
    le refus n'est pas un artefact global du montage."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_caster_reason

    _duel(["act", "endturn", "--state-file", str(STATE), "--runner", str(rid)])
    _duel(["aiturn", "--state-file", str(STATE), "--runner", str(rid)])
    st_after, _b = offline_state(capture(rid))
    us = units_by_vid(rid)
    if not (us.get(caster_a) or {}).get("hasAction"):
        fails.append("E-GATE: l'unite enfouie n'a pas repris la main au tour suivant -- "
                     "l'anti-confond ne tient pas")
    x = _cross(rid, caster_a, caster_b)
    nat_a, nat_b = x[(BURROWERS, "enfoui")], x[(BURROWERS, "temoin")]
    ab = ABILITY_CLASSES[BURROWERS]()
    port_a = int(get_invalid_caster_reason(st_after, int(caster_a), ab))
    port_b = int(get_invalid_caster_reason(st_after, int(caster_b), ab))
    if nat_a != 0x1 or nat_b != 0:
        fails.append("E-GATE natif au tour+1 : enfoui=%s temoin=%s (attendu 0x1 / 0x0) -- la "
                     "matrice a bouge, le confond « action consommee » n'est pas ecarte"
                     % (hex(nat_a), hex(nat_b)))
    if port_a != 0x40000000:
        fails.append("E-GATE port: l'unite ENFOUIE rend %s (attendu 0x40000000 AllowNullCasterTile "
                     "-- la clause TUILE-NULLE)" % hex(port_a))
    if port_b != 0:
        fails.append("E-GATE port: le TEMOIN rend %s (attendu 0)" % hex(port_b))
    if (port_a != 0) != (nat_a != 0) or (port_b != 0) != (nat_b != 0):
        fails.append("E-GATE VERDICTS divergents : enfoui port=%s natif=%s | temoin port=%s natif=%s"
                     % (hex(port_a), hex(nat_a), hex(port_b), hex(nat_b)))
    print("[E-GATE] tour+1 -- 1023 ENFOUI : natif=%s (etage AttackQuery) port=%s (clause "
          "tuile-nulle) -> tous deux REFUSENT" % (hex(nat_a), hex(port_a)))
    print("[E-GATE] tour+1 -- 1023 TEMOIN : natif=%s port=%s -> tous deux ACCEPTENT"
          % (hex(nat_b), hex(port_b)))


# --------------------------------------------------------------------------- montage nomme

def run(seed: str, board_id: str, keep: bool = False) -> dict:
    """MONTAGE NOMME d'UN couple (board, seed), reutilisable depuis pytest (cf.
    `tests/engine/runner/test_366_r1_burrowers_live.py`). Rend le dict de mesure ; `fails` y est la
    liste des ECARTS."""
    fails: list = []
    rid = build(seed, board_id)
    try:
        us = units_by_vid(rid)
        caster_a = next(i for i, u in us.items() if u["vid"] == GRAFT_A)
        caster_b = next(i for i, u in us.items() if u["vid"] == GRAFT_B)
        out = confront(rid, caster_a, fails)
        out.pop("state", None)
        e_swap(rid, caster_a, caster_b, fails)
        e_gate(rid, caster_a, caster_b, fails)      # DERNIER : il consomme un tour complet
        out.update({"rid": rid, "board": board_id, "seed": seed,
                    "caster_a": caster_a, "caster_b": caster_b, "fails": fails})
        return out
    finally:
        if not keep:
            _duel(["dispose", "--state-file", str(STATE), "--runner", str(rid)])


# --------------------------------------------------------------------------- main

def main() -> int:
    keep = "--keep" in sys.argv
    all_fails: list = []
    for board_id, seed in COUPLES:
        print()
        print("=== couple board=%s seed=%s ===" % (board_id, seed))
        out = run(seed, board_id, keep=keep)
        print("[burrow] runner %d | caster=%d(%s) temoin=%d(%s)"
              % (out["rid"], out["caster_a"], GRAFT_A, out["caster_b"], GRAFT_B))
        all_fails += ["[%s/%s] %s" % (board_id, seed, f) for f in out["fails"]]
    print()
    if all_fails:
        print("[burrow] %d ECHEC(S) :" % len(all_fails))
        for f in all_fails:
            print("   - " + f)
        return 1
    print("[burrow] OK -- CONFRONTATION port<->natif du cast de 1023 sur %d couples (board, seed) : "
          "pos/feet/alive/effet 1040 identiques terme a terme ; echange d'ability 1023<->1024 mesure ;"
          " verdicts identiques sur le second cast." % len(COUPLES))
    print("[burrow] NON COUVERT : (a) le 2e refus de `GetDynamicInvalidCasterReason` "
          "(`TileExtensions$$IsTemporary` sur les tuiles du caster) -- `isTemporary` n'est pas seede "
          "cote RUNNER, degradation PERMISSIVE ; (b) `RemoveAllForcedAttackTargets` sur un caster "
          "REELLEMENT sous Taunt / InstinctiveBehaviour ; (c) l'echange d'ability 1023 -> 1024 "
          "(couche `ActiveAbilityComponent` / `ActiveAbility$$get_CanCurrentlyBeUsed`) ; (d) "
          "l'ability 1024 `Burrowers_Appear` elle-meme. (c) et (d) sont des residus NOMMES.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
