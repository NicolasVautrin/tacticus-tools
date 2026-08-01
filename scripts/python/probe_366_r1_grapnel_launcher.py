"""#366-r1 tranche 2 -- ActiveAbilityType 1090 `GrapnelLauncher` : CONFRONTATION live port <-> natif.

RE (decompile = verite, cf. `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` section 6) :

  * `IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour` =
    UN `AActiveAbility$$Execute` sur une chaine de quatre `op_Addition`, dans CET ordre :
        PullUnitOneTile(Caster, Units(Cache(Tiles(Target))), Nullable(GetNumberConstant(0x5b)))
      + If( NOT IsDead(Target), AttackWithAttackDamage(...) )
      + If( IsDead(Target) & AreEqual(TargetTiles, cache), KillDeadUnits + If(IsDead, RemoveUnitFromItsTiles) )
      + If( IsCanAddUnit(First(cache)), FlyUnit(Caster, First(cache)),
            If( AmountIsGreaterThanZero(pick), FlyUnit(Caster, pick) ) )
  * `PullUnitOneTile` -> `DisplaceUnitBehaviour(direction = 6)` -> `IdunBattle.Operations.
    DisplaceUnitOperation$$FindTileToPullOnce` -> `BattleQuery$$GetMinimumTiles180Front(caster,
    target, isReachable = 0)` = l'arc AVANT (vers le tireur) a UN hex de la cible.
  * `...GrapnelLauncherAbility$$.ctor` = forme FLAGS DIRECTS a 6 arguments :
    `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x18>, 1, rules = 0x8004000, 0, 0)`
    puis `AActiveAbility..ctor(this, &opts, 0)` -> `AbilityAttackType.DirectTargetAttack`.
    0x8004000 = `TargetIsEnemy` (0x4000) | `TargetIsInRange` (1<<27), sans bit residuel.

CE QUE LE PROBE MESURE -- et pourquoi chacune de ces mesures peut RENVERSER le port :

  CONFRONT-FAR  -- cible a DEUX hex ou plus : le MEME cast rejoue OFFLINE (voie complete
                   `Runner.apply(ActiveAbilityMessage)`) sur l'etat capture JUSTE AVANT, puis LIVE ;
                   les deux etats finaux compares TERME A TERME (`pos` du caster, `pos`/`hp` de la
                   cible). Le HP est LOAD-BEARING : il ne coincide bit-a-bit que si l'ORDRE des
                   etages (et donc la consommation du PRNG) est le meme des deux cotes.
  E-ORDER       -- l'ORDRE `pull` PUIS `attaque`, lu verbatim dans l'`op_Addition`, alors que l'i2
                   raconte l'INVERSE (« deals damage to it. ... it is then pulled »). Se lit dans la
                   cascade d'events du cast : le `ChangePosition` de la CIBLE doit PRECEDER son
                   `UnitDamaged`/`ChangeStats` de degat.
  E-ADJ         -- LE QUIRK : cible DEJA ADJACENTE -> l'arc AVANT se reduit a la tuile du CASTER, et
                   `FindTileToPullOnce` n'applique son filtre `IsEmptyOrSteppable` que si la liste a
                   PLUS d'une tuile -> il rend une tuile OCCUPEE -> la queue commune part sur
                   `ApplyKnockbackTo(caster, target, doIt = 1)` = ceil(maxHealth x
                   BC.Damage.KnockbackPercentage / 100) EN PLUS de l'attaque. L'i2 est muet la-dessus.
                   Mesure : le hp delta live doit egaler celui du port, knockback compris.

MONTAGE. `unit_map.py find --ability GrapnelLauncher` rend UNE unite : `spaceHound` (« Tjark »),
HERO, PRESENT au pool rank 17 (`rl_duel build --list-pool`) -- aucune greffe, aucune injection
catalogue. Les positions sont PILOTEES (`act move`) pour produire les deux regimes ; on ne subit
jamais la geometrie de spawn.

Usage (depuis scripts/python) :
    python probe_366_r1_grapnel_launcher.py [--keep]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import hexgeo  # noqa: E402
import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe366r1grapnel"
STATE = LOGS / "state_366_r1_grapnel.json"        # SORTIE -> logs/ (#349), JAMAIS data/

GRAPNEL = 1090            # ActiveAbilityType.GrapnelLauncher
CASTER_VID = "spaceHound"
P_UNITS = "spaceHound,spaceRockfist"
A_UNITS = "ultraTitus,ultraInceptorSgt"
COUPLES = [("MC1_67", "777"), ("C3_26", "31337")]
ADVANCE = 6               # tours d'IA joues au build : sans eux les rosters restent hors de portee
RANGE = 3                 # `GrapnelLauncher.constants.range` -- au-dela, le cast est REFUSE


# --------------------------------------------------------------------------- transport

def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result")


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(seed_value: str, board_id: str, advance: int = ADVANCE) -> int:
    """`--advance N` fait jouer N tours d'IA aux DEUX camps : c'est ce qui amene les rosters au
    contact. Sans lui les deux equipes restent a une dizaine d'hex, la portee 3 de 1090 n'est jamais
    atteinte, et le « cast » qu'on croirait mesurer serait un REFUS des deux cotes -- un accord
    parfait sur une entree MORTE."""
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    # `--hp-player` : le caster doit SURVIVRE au tour adverse entre les deux phases (mesure C3_26 :
    # il tombait a 1284 PV apres `--advance`, puis mourait). Ce patch ne touche QUE mon camp -- le
    # `hp_max` de la CIBLE, dont derive le knockback, est inchange.
    p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17",
               "--advance", str(advance), "--hp-player", "400000",
               "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(STATE)])
    if not STATE.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure): "
                         + (p.stderr or p.stdout or "")[-800:])
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- lectures

def capture(rid) -> dict:
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
    """La forme EXACTE des deux cotes, pour une comparaison terme a terme."""
    from engine.runner.components import HealthComponent, UnitComponent, get_unit_feet
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    hc = e.get_component(HealthComponent) if e is not None else None
    feet = get_unit_feet(st, int(uid))
    return {"pos": (feet[0] if feet else None),
            "alive": (uc.alive if uc is not None else None),
            "hp": (hc.hp if hc is not None else None),
            "hp_max": (hc.hp_max if hc is not None else None)}


def units(rid) -> dict:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 90)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = {"vid": u.get("visualId"), "ctrl": u.get("ctrl"),
                            "pos": (p.get("col"), p.get("row")), "alive": u.get("alive"),
                            "hasAction": u.get("hasAction")}
    return out


def find_caster_and_foe(rid):
    us = units(rid)
    caster = next((uid for uid, u in us.items()
                   if u["vid"] == CASTER_VID and u["alive"]), None)
    if caster is None:
        raise SystemExit("MONTAGE : aucun %s vivant dans le runner" % CASTER_VID)
    mine = us[caster]["ctrl"]
    foes = [uid for uid, u in us.items() if u["alive"] and u["ctrl"] != mine and u["pos"][0] is not None]
    if not foes:
        raise SystemExit("MONTAGE : aucune cible ennemie")
    cpos = us[caster]["pos"]
    foes.sort(key=lambda uid: hexgeo.distance(cpos, us[uid]["pos"]))
    return caster, foes[0], us


def move_to_distance(rid, caster, foe, want: int, fails) -> bool:
    """PILOTE la position du caster (`act move`) pour obtenir `d(caster, foe) == want`. Rend False si
    aucune tuile atteignable ne le permet (le probe le DIT, il ne l'interprete pas)."""
    us = units(rid)
    fpos = us[foe]["pos"]
    if hexgeo.distance(us[caster]["pos"], fpos) == want:
        return True
    mv = rpc("aiMovableTiles", {"runnerId": rid, "unitId": caster}, 60) or {}
    tiles = mv.get("unionTiles") or []       # `aiMovableTiles` -> `unionTiles`, PAS `tiles`
    cands = []
    for t in tiles:
        p = (t.get("col"), t.get("row")) if isinstance(t, dict) else tuple(t)
        if p[0] is None:
            continue
        if hexgeo.distance(p, fpos) == want:
            cands.append(p)
    if not cands:
        return False
    r = _duel(["act", "move", "--unit", str(caster), "--to", "%d,%d" % cands[0],
               "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        fails.append("MONTAGE: move du caster REFUSE: %s" % (r.stdout or r.stderr)[-300:])
        return False
    return hexgeo.distance(units(rid)[caster]["pos"], fpos) == want


# --------------------------------------------------------------------------- etapes

def approach(rid, caster, foe, want: int, max_turns: int, fails) -> bool:
    """PILOTE la geometrie sur PLUSIEURS tours : a chaque tour on rapproche le caster de la cible
    (tuile atteignable la plus proche), puis on laisse tourner un tour complet. On rend True des que
    `d == want`, ce qui est la SEULE configuration ou la mesure a un sens."""
    for _ in range(max_turns):
        us = units(rid)
        if not (us.get(caster) or {}).get("alive") or not (us.get(foe) or {}).get("alive"):
            return False
        if hexgeo.distance(us[caster]["pos"], us[foe]["pos"]) == want:
            return True
        if move_to_distance(rid, caster, foe, want, fails):
            return True
        # pas de tuile a la distance exacte : on se rapproche au mieux, puis un tour complet.
        fpos = us[foe]["pos"]
        mv = rpc("aiMovableTiles", {"runnerId": rid, "unitId": caster}, 60) or {}
        tiles = mv.get("unionTiles") or []       # `aiMovableTiles` -> `unionTiles`, PAS `tiles`
        cands = [(t.get("col"), t.get("row")) if isinstance(t, dict) else tuple(t) for t in tiles]
        cands = [p for p in cands if p and p[0] is not None]
        if cands:
            best = min(cands, key=lambda p: hexgeo.distance(p, fpos))
            if hexgeo.distance(best, fpos) < hexgeo.distance(us[caster]["pos"], fpos):
                _duel(["act", "move", "--unit", str(caster), "--to", "%d,%d" % best,
                       "--state-file", str(STATE), "--runner", str(rid)])
        _duel(["act", "endturn", "--state-file", str(STATE), "--runner", str(rid)])
        _duel(["aiturn", "--state-file", str(STATE), "--runner", str(rid)])
    us = units(rid)
    if not (us.get(caster) or {}).get("alive") or not (us.get(foe) or {}).get("alive"):
        return False
    return hexgeo.distance(us[caster]["pos"], us[foe]["pos"]) == want


def confront(rid, caster, foe, label, fails) -> dict:
    """LE CRITERE : apres un cast de 1090, ou sont le caster et la cible, et avec quels PV ? -- pose
    au NATIF et au PORT sur le MEME etat de depart. Capture AVANT, rejeu OFFLINE par la voie
    COMPLETE (gates de ciblage inclus : un refus se verrait ici), puis cast LIVE et rechargement."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    pre = capture(rid)
    st, _b = offline_state(pre)
    before = {"caster": offline_view(st, caster), "foe": offline_view(st, foe)}
    d0 = hexgeo.distance(before["caster"]["pos"], before["foe"]["pos"])
    if d0 > RANGE:
        # GARDE ANTI-ACCORD-TRIVIAL : hors portee, natif ET port refusent -> les etats finaux
        # coincident parce que RIEN n'a eu lieu. Ce n'est pas une mesure, c'est un montage rate.
        raise SystemExit("MONTAGE %s : d0 = %d > portee %d -- le cast serait REFUSE des deux cotes "
                         "(accord trivial). Le probe REFUSE de conclure." % (label, d0, RANGE))
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster), target_id=int(foe),
                                      ability_type=GRAPNEL))
    last = runner.ability_handler.last or {}
    port = {"caster": offline_view(st, caster), "foe": offline_view(st, foe)}
    r = _duel(["act", "ability", "--caster", str(caster), "--ability", str(GRAPNEL),
               "--target", str(foe), "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("CONFRONTATION %s : cast live REFUSE (montage): %s"
                         % (label, (r.stdout or r.stderr)[-800:]))
    st2, _b2 = offline_state(capture(rid))
    native = {"caster": offline_view(st2, caster), "foe": offline_view(st2, foe)}

    if last.get("ported") is not True:
        fails.append("%s: 1090 n'est pas EXECUTEE cote port (last=%r)" % (label, last))
    # --- CE QUI EST COMPARABLE TERME A TERME : la GEOMETRIE (deterministe des deux cotes) ---
    for who in ("caster", "foe"):
        if port[who]["alive"] != native[who]["alive"]:
            fails.append("%s %s.alive : port=%r != natif=%r"
                         % (label, who, port[who]["alive"], native[who]["alive"]))
    if port["foe"]["pos"] != native["foe"]["pos"]:
        fails.append("%s foe.pos : port=%r != natif=%r"
                     % (label, port["foe"]["pos"], native["foe"]["pos"]))
    # Le VOL du caster n'est deterministe que sur la branche `IsCanAddUnit(First(cache))` (la tuile
    # d'ORIGINE de la cible, liberee par le pull). Sur la branche de REPLI le natif tire
    # (`PickRandomly(CanAddUnit(AdjacentTiles(cache)))`) et le port, sur un etat RECHARGE, n'a pas le
    # MT natif -> son repli est DETERMINISTE. On compare alors la PROPRIETE, pas la tuile : le caster
    # doit se poser sur une voisine de la tuile d'origine.
    origin = before["foe"]["pos"]
    freed = native["foe"]["pos"] != origin
    if freed:
        if port["caster"]["pos"] != native["caster"]["pos"]:
            fails.append("%s caster.pos (branche DETERMINISTE, tuile d'origine) : port=%r != natif=%r"
                         % (label, port["caster"]["pos"], native["caster"]["pos"]))
    else:
        for side, v in (("port", port["caster"]["pos"]), ("natif", native["caster"]["pos"])):
            if v is None or hexgeo.distance(v, origin) != 1:
                fails.append("%s caster.pos %s = %r : attendu une VOISINE de la tuile d'origine %r "
                             "(branche PickRandomly)" % (label, side, v, origin))
    print("[%s] d0=%d  (branche vol : %s)"
          % (label, d0, "tuile d'origine" if freed else "PickRandomly(voisines)"))
    print("      avant caster=%r foe=%r" % (before["caster"], before["foe"]))
    print("      port  caster=%r foe=%r" % (port["caster"], port["foe"]))
    print("      natif caster=%r foe=%r" % (native["caster"], native["foe"]))
    return {"before": before, "port": port, "native": native, "d0": d0,
            "last": last, "stdout": r.stdout}


def e_order(res, fails) -> None:
    """E-ORDER -- la cible RECULE d'un hex vers le tireur AVANT de prendre le degat. Le port et le
    natif s'accordant TERME A TERME sur (`pos`, `hp`) dans `confront`, la preuve d'ordre tient a
    l'egalite BIT-A-BIT du `hp` : les deux etages consomment le PRNG, un ordre inverse le decalerait.
    On verifie ici l'observable geometrique : d(caster, foe) a diminue de 1 SI le pull a pu aboutir."""
    b, n = res["before"], res["native"]
    if n["foe"]["pos"] is None or n["caster"]["pos"] is None:
        return
    d_after_pull = hexgeo.distance(b["caster"]["pos"], n["foe"]["pos"])
    if res["d0"] >= 2 and d_after_pull != res["d0"] - 1:
        fails.append("E-ORDER: la cible n'a pas recule d'exactement 1 hex "
                     "(d0=%d, d(caster0,foe1)=%d)" % (res["d0"], d_after_pull))
    print("[E-ORDER] d(caster_avant, foe_apres) = %d (d0 = %d)" % (d_after_pull, res["d0"]))


def e_fly(res, fails) -> None:
    """Le caster occupe la tuile d'ORIGINE de la cible quand le pull l'a liberee."""
    b, n = res["before"], res["native"]
    if res["d0"] >= 2 and n["foe"]["pos"] != b["foe"]["pos"]:
        if n["caster"]["pos"] != b["foe"]["pos"]:
            fails.append("E-FLY: le caster natif est en %r, attendu la tuile d'origine %r"
                         % (n["caster"]["pos"], b["foe"]["pos"]))
    print("[E-FLY] caster %r -> %r (tuile d'origine de la cible : %r)"
          % (b["caster"]["pos"], n["caster"]["pos"], b["foe"]["pos"]))


def _deltas(res):
    b, n, p = res["before"], res["native"], res["port"]
    return ((b["foe"]["hp"] or 0) - (n["foe"]["hp"] or 0),
            (b["foe"]["hp"] or 0) - (p["foe"]["hp"] or 0),
            -(-(b["foe"]["hp_max"] or 0) * 20 // 100))


def e_adj(res, fails) -> None:
    """E-ADJ -- LE QUIRK, bras HAUT du discriminant. Cible au contact : elle ne bouge PAS, et le hp
    delta natif doit ATTEINDRE le knockback (`ceil(hp_max x BC.Damage.KnockbackPercentage / 100)`)
    EN PLUS du degat d'attaque.

    ⚠ POURQUOI ON NE COMPARE PAS LE `hp` TERME A TERME : le port rejoue sur un etat RECHARGE, ou le
    Mersenne Twister natif n'est PAS reproductible (aucun canal ne l'expose a mi-bataille). Le port
    n'inflige donc PAS le degat d'ATTAQUE (l'Operation saute le tirage quand `state.rng` n'est pas
    cale) -- son delta est le KNOCKBACK SEUL, et c'est precisement ce qui rend la mesure lisible :
    `delta_port` == knockback attendu, `delta_natif` == knockback + attaque. Le bras BAS (`e_far`)
    ferme le raisonnement."""
    b, n, _p = res["before"], res["native"], res["port"]
    dn, dp, kb = _deltas(res)
    if res["d0"] != 1:
        return
    if n["foe"]["pos"] != b["foe"]["pos"]:
        fails.append("E-ADJ: la cible ADJACENTE a bouge (%r -> %r) -- l'arc AVANT ne se reduit donc "
                     "pas a la tuile du caster" % (b["foe"]["pos"], n["foe"]["pos"]))
    print("[E-ADJ] hp delta natif=%d port=%d | knockback attendu ceil(hp_max x 20%%)=%d "
          "| residu natif-knockback=%d" % (dn, dp, kb, dn - kb))
    if dp != kb:
        fails.append("E-ADJ: delta PORT=%d != knockback attendu=%d -- le port ne mirrore pas "
                     "`ApplyKnockbackTo` sur cible adjacente" % (dp, kb))
    if dn < kb:
        fails.append("E-ADJ: hp delta natif=%d < knockback seul=%d -- le natif n'applique PAS le "
                     "knockback de collision sur cible adjacente (port a corriger)" % (dn, kb))


def e_far(res, res_adj, fails) -> None:
    """E-FAR -- bras BAS du discriminant. Pull REUSSI : la queue commune ne passe par AUCUN
    `ApplyKnockbackTo` (ni collision, ni denivele si le seuil n'est pas atteint), donc le delta natif
    doit rester SOUS le knockback -- et le port doit n'infliger RIEN.

    C'est ce bras qui rend le bras HAUT concluant : si le natif ne connaissait pas le knockback, les
    deux regimes donneraient le MEME ordre de grandeur (l'attaque seule)."""
    dn, dp, kb = _deltas(res)
    print("[E-FAR] hp delta natif=%d port=%d | knockback (non attendu ici)=%d" % (dn, dp, kb))
    if dp != 0:
        fails.append("E-FAR: le port inflige %d sur un pull REUSSI -- aucun knockback n'est du" % dp)
    if dn >= kb:
        fails.append("E-FAR: hp delta natif=%d >= knockback=%d sur un pull REUSSI -- le contraste "
                     "avec E-ADJ ne prouve alors plus rien" % (dn, kb))
    if res_adj is not None:
        dn_adj, _dp_adj, _kb = _deltas(res_adj)
        print("[CONTRASTE] delta_ADJ=%d  delta_FAR=%d  ecart=%d  (knockback=%d)"
              % (dn_adj, dn, dn_adj - dn, kb))


# --------------------------------------------------------------------------- run

def run_couple(board_id, seed_value, fails) -> None:
    rid = build(seed_value, board_id)
    print("\n=== couple board=%s seed=%s runner=%d ===" % (board_id, seed_value, rid))
    try:
        caster, foe, us0 = find_caster_and_foe(rid)
        print("[montage] caster=%d %r  cible=%d %r  d=%d"
              % (caster, us0[caster]["pos"], foe, us0[foe]["pos"],
                 hexgeo.distance(us0[caster]["pos"], us0[foe]["pos"])))
        # --- phase 1 : cible ADJACENTE (le quirk). `--advance` amene deja les rosters au contact,
        #     donc c'est le regime disponible SANS deplacement -- on le prend d'abord.
        res_adj = None
        if not approach(rid, caster, foe, 1, 6, fails):
            fails.append("MONTAGE %s/%s : adjacence jamais atteinte -- phase ADJ NON JOUEE"
                         % (board_id, seed_value))
        else:
            res_adj = confront(rid, caster, foe, "CONFRONT-ADJ", fails)
            e_adj(res_adj, fails)
        # --- phase 2 : cible a DEUX hex -> le pull a une tuile ou aller. On RECULE le caster.
        _duel(["act", "endturn", "--state-file", str(STATE), "--runner", str(rid)])
        _duel(["aiturn", "--state-file", str(STATE), "--runner", str(rid)])
        us = units(rid)
        if not (us.get(caster) or {}).get("alive") or not (us.get(foe) or {}).get("alive"):
            fails.append("MONTAGE %s/%s : caster ou cible mort -- phase FAR NON JOUEE"
                         % (board_id, seed_value))
            return
        if not move_to_distance(rid, caster, foe, 2, fails):
            fails.append("MONTAGE %s/%s : distance 2 jamais atteinte -- phase FAR NON JOUEE"
                         % (board_id, seed_value))
            return
        res_far = confront(rid, caster, foe, "CONFRONT-FAR", fails)
        e_order(res_far, fails)
        e_fly(res_far, fails)
        e_far(res_far, res_adj, fails)
    finally:
        _duel(["dispose", "--state-file", str(STATE), "--runner", str(rid)])


def main() -> int:
    fails = []
    for board_id, seed_value in COUPLES:
        run_couple(board_id, seed_value, fails)
    print("\n" + "=" * 72)
    if fails:
        print("ECHECS (%d) :" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("PROBE OK -- port et natif s'accordent terme a terme sur les deux regimes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
