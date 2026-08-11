"""#924 -- CONFRONT LIVE des faces PORTEES d'`InescapableDeath` (passif de `necroDestroyer`).

`necroDestroyer` (Imospekh) porte le trait `Overwatch` NATIVEMENT : il n'a donc rien a caster,
l'effet 1009 `Overwatch_AutoAttack` ET l'effet 1018 `InescapableDeath_Effect` sont poses au SPAWN.
C'est ce qui distingue ce montage de celui de sa soeur de forme 1145 (`tauCrisis`), ou l'overwatch
n'existe qu'apres le cast de l'actif 1077.

Les DEUX faces portees, et ce que chaque test rendrait si le port ne faisait rien :

  A. INIT OWNER (`AOwnerEffectTriggeredAbility$$CreateTrigger` = `OnOwnerSpecificAbilityInit`) --
     1018 present sur le porteur, live ET offline. Sans la face : absent offline.
  B. LES DEUX `Triggered()` heritees (`AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal`)
     -- un kill EN OVERWATCH pose 1019 `InescapableDeath_HitsReduction` (`EXTRA_HITS -1`) et
     l'overwatch reste ARME. Sans la face : 1019 absent offline.

La 3e face (DEGAT, `CreateDamageModifier`) est RE-solue et MESUREE mais **non portee** : son etage
d'injection est invalide par la mesure (residu #924-r2). Elle n'a donc pas de confront ici -- le
cliquet qui la garde desarmee vit dans `tests/engine/test_924_inescapable_death_offline.py`, et
toute la mesure est en §6 de `engine/entities/effects/loki/inescapable_death.py`.

Drive les positions ; lit l'etat LIVE ; state-files uniques ; ASCII-only.
"""
from __future__ import annotations

import pytest

import hexgeo

OVERWATCH_AUTO_ATTACK = 1009           # EffectType.Overwatch_AutoAttack
INESCAPABLE_DEATH_EFFECT = 1018        # EffectType.InescapableDeath_Effect
INESCAPABLE_DEATH_HITS_RED = 1019      # EffectType.InescapableDeath_HitsReduction
DESTROYER = "necroDestroyer"
BOARD = "MC1_67"

DECLENCHEUR = {
    "chemins": (
        # Les deux faces confrontees ici.
        "scripts/python/engine/entities/effects/loki/inescapable_death.py",
        "scripts/python/engine/runner/operations/triggers/loki/reactivate_overwatch.py",
        # Les registres qui posent l'effet (face A) et branchent les triggers (face B).
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # La pose au SPAWN de l'effet owner : c'est le vecteur de la face A cote port.
        "scripts/python/engine/runner/operations/spawn.py",
        # Le seed d'etat depuis le live (les deux canaux de `decisionView` y sont consommes).
        "scripts/python/engine/runner/snapshot.py",
        # Le vecteur OVERWATCH : il pose `triggering_ability=1009`, sans quoi `LegitDeathReasons`
        # ne peut pas etre satisfait cote port.
        "scripts/python/engine/runner/operations/triggers/effect_triggers.py",
        # Le canal qui grave la raison de mort confrontee par la face B.
        "scripts/python/engine/runner/operations/damage.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confront LIVE des deux faces PORTEES d'`InescapableDeath` : la pose de l'effet 1018 "
              "au spawn (lue sur le canal `includeInactive`, le canal par defaut droppant les "
              "instances inertes) et la pose de 1019 par le kill en overwatch (tranchee par le "
              "RETOUR du `applyAction`, l'effet pouvant EXPIRER avant qu'on relise l'etat).",
}


# ------------------------------------------------------------------ harnais (idem test_tau_lot1_residues)

@pytest.fixture(scope="module")
def rpc_(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return Board(bg["tiles"], adjacency="evenq")


def _load(rpc, rid, board):
    from engine.runner.snapshot import load_state
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board), dec


def _dec(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _dec_all(rpc, rid):
    """MEME vue, canal `includeInactive` -- celui qui publie les instances PRESENTES MAIS INERTES.

    ⚠ Le canal par DEFAUT filtre `IsActive` et **droppe** ces instances : y lire une absence ne
    prouve donc RIEN sur l'existence de l'effet cote natif. C'est exactement le regime du spawn --
    `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` DESACTIVE l'overwatch pendant le
    tour de son porteur (`On(0x12) & IsTurnOf(owner) -> DeactivateEffect`), donc 1009 est absent du
    canal par defaut tant que le tour n'a pas tourne."""
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                "includeInactive": True}, 90)


def _units(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vid):
    return next((u for u in _units(dec).values() if u.get("visualId") == vid), None)


def _effs_live(dec, uid) -> dict:
    u = _units(dec).get(int(uid))
    return {int(e["effectType"]): e.get("remaining") for e in ((u or {}).get("effects") or [])
            if e.get("effectType") is not None}


def _effs_off(state, uid) -> dict:
    effs = (state.effects.by_unit if state.effects is not None else {}).get(int(uid), [])
    return {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
            for e in effs if not e.consumed}


def _movable(rpc, rid, uid):
    mv = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    row = next((u for u in (mv.get("units") or []) if u.get("unitId") == uid), None)
    return [(t.get("col"), t.get("row")) for t in ((row or {}).get("tiles") or [])]


def _move(rpc, rid, uid, to):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 90)


def _endturn(rpc, rid, n=1):
    for _ in range(n):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _hp_live(rpc, rid) -> dict:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u["squadId"]: (u["hp"], u.get("isDead")) for u in (ob.get("units") or [])}


def _max_range(vid: str) -> int:
    import gameconfig as GC
    ws = (GC.unit(vid) or {}).get("weapons") or []
    return max([int(w.get("Range") or 0) for w in ws] or [0]) or 1


def _effets_poses_par(move_res) -> set:
    """Les NOMS d'effets que la reponse `applyAction` declare avoir poses pendant CE move.

    ⚠ C'est le RETOUR de l'action, pas l'etat d'apres : un effet a duree
    `TurnsUntilUnitOwnerTurn` peut avoir EXPIRE entre le move et la lecture (le tour bascule tout
    seul quand la derniere unite adverse a agi). Lire l'etat final ferait alors conclure << le natif
    n'a rien pose >> a partir d'un simple retard de mesure. Les events, eux, sont l'enregistrement
    de ce qui s'est produit."""
    noms = set()
    for a in ((move_res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("kind") == "group" and e.get("source"):
                noms.add(str(e["source"]))
    return noms


def _hp_off(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else int(hc.hp)


# ============================================================== A. l'effet 1018 est pose a l'INIT

def test_924_effet_pose_sur_le_porteur_au_spawn_live(rpc_, build_runner):
    """Face A -- `AOwnerEffectTriggeredAbility$$CreateBehaviour` = `AddEffect(0x3fa, ..., owner,
    owner)` sur `OnOwnerSpecificAbilityInit`. Aucun cast, aucune condition d'etat : l'effet EST la
    des le spawn, des DEUX cotes.

    ⚠ MESURE, PAS SUPPOSITION -- ce test lit les DEUX canaux. Au spawn on est dans le TOUR du
    porteur, et `RangedAutoAttackEffect` y DESACTIVE l'overwatch : le canal par defaut de
    `decisionView` (filtre `IsActive`) rend alors `[1011]` seulement. Conclure de la que le natif
    ne pose ni 1009 ni 1018 serait faux -- c'est le canal `includeInactive` qui tranche."""
    rid = build_runner("9241", ["--p-units", f"{DESTROYER},necroWarden",
                                "--a-units", "orksNob,orksNob", "--no-ai"], board=BOARD)["rid"]
    board = _board(rpc_, rid)
    dec = _dec(rpc_, rid)
    d = _find(dec, DESTROYER)
    assert d is not None, f"{DESTROYER} absent du runner"
    uid = d["id"]

    actifs = _effs_live(dec, uid)                       # canal filtre IsActive
    tous = _effs_live(_dec_all(rpc_, rid), uid)         # canal includeInactive
    state, _ = _load(rpc_, rid, board)
    off = _effs_off(state, uid)
    print(f"\n[1018] u{uid} live(actifs)={sorted(actifs)}\n"
          f"       live(tous)  ={sorted(tous)}\n"
          f"       off         ={sorted(off)}")

    assert tous != actifs or OVERWATCH_AUTO_ATTACK in actifs, \
        (f"les deux canaux rendent la MEME chose ({sorted(tous)}) -- `includeInactive` ne publie "
         f"plus les instances inertes, ce test ne mesure plus ce qu'il croit")
    assert INESCAPABLE_DEATH_EFFECT in tous, \
        (f"le natif ne pose PAS 1018 au spawn, meme sur le canal `includeInactive` "
         f"(effets={sorted(tous)}) -- `InescapableDeathAbility$$GetEffectType` = 0x3fa, RE a revoir")
    assert OVERWATCH_AUTO_ATTACK in tous, \
        (f"le natif ne pose PAS 1009 sur {DESTROYER} au spawn (effets={sorted(tous)}) -- "
         f"le trait Overwatch du kit a change, RE a revoir")
    assert INESCAPABLE_DEATH_EFFECT in off, \
        (f"le port n'a PAS pose 1018 sur le porteur (effets={sorted(off)}) -- "
         f"`ABILITY_INIT_OWNER_EFFECTS['InescapableDeath']` manquant ou non seede")


# ==================================================== B + C. le tir d'overwatch : degats, puis kill

def _replay(state, foe_id, tile, mt):
    """Rejoue le MEME `MoveUnitMessage` sur un etat FRAIS, MT cale au point ou le live etait juste
    avant le move (l'overwatch est le 1er consommateur de RNG)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(mt["mt"])
    rng.mti = mt["mti"]
    state.rng = rng
    Runner(state).install_default_handlers(20).apply(MoveUnitMessage(foe_id, tile))
    return state


def _drive_overwatch_shot(rpc, rid, board, uid):
    """DRIVE partage : approche `necroDestroyer` des ennemis en restant HORS de sa portee de tir,
    puis fait entrer un ennemi d'UN PAS dedans -- le vecteur after-move declenche l'overwatch.

    Rend l'etat capture AVANT le move (NON rejoue) + le MT, pour que l'appelant puisse rejouer
    autant de fois qu'il veut (replay nominal, puis MUTANT). None si le scenario n'est pas atteint.
    """
    import copy

    dec = _dec(rpc, rid)
    me = _units(dec)[uid]
    my_player, my_team = me.get("owner"), me.get("team")
    R = _max_range(DESTROYER)
    FOE_MOVE = 4

    for _ in range(10):
        dec = _dec(rpc, rid)
        if not dec.get("ok", True) or _units(dec).get(uid) is None:
            return None
        mypos = _pos(_units(dec)[uid])
        hp = _hp_live(rpc, rid)
        foes = [u for u in _units(dec).values()
                if u.get("team") != my_team and hp.get(u["id"], (0, None))[0] > 0]
        if not foes:
            return None

        if dec.get("currentPlayer") == my_player:
            near = min(foes, key=lambda f: hexgeo.distance(mypos, _pos(f)))
            if hexgeo.distance(mypos, _pos(near)) > FOE_MOVE + R:
                cands = [q for q in _movable(rpc, rid, uid)
                         if hexgeo.distance(q, _pos(near)) > R]      # rester HORS de portee
                if cands:
                    _move(rpc, rid, uid, min(cands, key=lambda q: hexgeo.distance(q, _pos(near))))
            _endturn(rpc, rid, 1)
            continue

        # --- tour ADVERSE : faire entrer un ennemi dans la portee de tir ---
        effs = _effs_live(dec, uid)
        assert OVERWATCH_AUTO_ATTACK in effs and INESCAPABLE_DEATH_EFFECT in effs, \
            f"porteur pas en overwatch avec 1018 (effets={sorted(effs)}) -- scenario NON monte"
        assert INESCAPABLE_DEATH_HITS_RED not in effs, \
            f"1019 deja present AVANT le tir (effets={sorted(effs)}) -- l'oracle serait fausse"
        moved = False
        for foe in foes:
            tiles = _movable(rpc, rid, foe["id"])
            if not tiles:
                continue
            best = min(tiles, key=lambda q: hexgeo.distance(q, mypos))
            if hexgeo.distance(best, mypos) > R:
                _move(rpc, rid, foe["id"], best)
                moved = True
                continue
            # === capture AVANT le move (l'overwatch est le 1er consommateur de RNG) ===
            state, _d = _load(rpc, rid, board)
            s0 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not (isinstance(s0, dict) and s0.get("mt")):
                pytest.skip("dumpRng KO")
            off_before = _effs_off(state, uid)
            hp_foe_before = _hp_live(rpc, rid).get(foe["id"], (None, None))[0]
            # DEUX copies independantes du MEME etat : le replay nominal et le replay MUTANT
            # doivent partir du meme point, sinon la comparaison ne prouve rien.
            etats = [copy.deepcopy(state), copy.deepcopy(state)]

            move_res = _move(rpc, rid, foe["id"], best)            # === move LIVE ===
            hp_after_live = _hp_live(rpc, rid).get(foe["id"], (None, None))
            if hp_after_live[0] == hp_foe_before and not hp_after_live[1]:
                moved = True
                continue                                          # overwatch n'a pas tire
            return {"foe": foe["id"], "tile": best, "etats": etats, "mt": s0,
                    "off_before": off_before, "hp_before": hp_foe_before,
                    "hp_live": hp_after_live[0], "dead_live": bool(hp_after_live[1]),
                    "move_res": move_res}
        if not moved:
            return None
    return None


def test_924_kill_en_overwatch_pose_la_reduction_de_coups_live(rpc_, build_runner):
    """Face B -- Triggered #1 : `On(PreUnitDeath) & OwnerIsActor & NOT IsTurnOf(owner) &
    AmountIsGreater(Max(Ranged,Melee AttackHits), hitsReduction) & LegitDeathReasons`
    -> `ActivateEffect(1009) & AddStaticStatModifierEffect(1019, EXTRA_HITS, -hitsReduction,
    TurnsUntilUnitOwnerTurn)`.

    `LegitDeathReasons` est ici celui de la BASE (un seul terme, `HasDeathReason(dying, Ability,
    1009)`) -- la victime doit etre morte DU TIR D'OVERWATCH, pas d'autre chose.

    Les DEUX faces de la branche sont exercees : 1019 ABSENT avant (assertionne dans le drive),
    PRESENT apres -- live ET offline."""
    from engine.runner.components import StatsComponent, UnitComponent
    from engine.entities.stats import StatType

    rid = build_runner("9242", [
        "--p-units", f"{DESTROYER},necroWarden", "--a-units", "orksNob,orksNob",
        "--hp-target", "1"], board=BOARD)["rid"]
    board = _board(rpc_, rid)
    d = _find(_dec(rpc_, rid), DESTROYER)
    assert d is not None, f"{DESTROYER} absent du runner"
    uid = d["id"]

    fired = _drive_overwatch_shot(rpc_, rid, board, uid)
    if fired is None:
        pytest.fail("scenario NON atteint : aucun tir d'overwatch obtenu (drive des positions KO)")
    if not fired["dead_live"]:
        pytest.fail(f"le tir d'overwatch n'a pas TUE (hp={fired['hp_live']}) -- "
                    f"le montage `--hp-target 1` ne tient plus")

    state = _replay(fired["etats"][0], fired["foe"], fired["tile"], fired["mt"])
    off_after = _effs_off(state, uid)
    # MEME piege qu'au spawn : apres le kill la main revient au porteur, `RangedAutoAttackEffect`
    # DESACTIVE l'overwatch, et le canal filtre `IsActive` de `decisionView` rend `[]` -- ce qui se
    # lirait comme << le natif n'a rien pose >>. On lit le canal `includeInactive`, et on garde
    # l'autre pour l'afficher : la comparaison de PRESENCE se fait sur le canal qui publie tout.
    live_actifs = _effs_live(_dec(rpc_, rid), uid)
    live_after = _effs_live(_dec_all(rpc_, rid), uid)
    sc = state.get_entity(int(uid)).get_component(StatsComponent)
    extra_hits = int(sc.ctx.stat(StatType.EXTRA_HITS)) if sc is not None else None
    dead = state.get_entity(int(fired["foe"])).get_component(UnitComponent)
    print(f"\n[1019] u{uid} tue u{fired['foe']} en {fired['tile']}\n"
          f"       off  {sorted(fired['off_before'])} -> {sorted(off_after)}\n"
          f"       live(tous)={sorted(live_after)} live(actifs)={sorted(live_actifs)}\n"
          f"       EXTRA_HITS offline={extra_hits} death_source={getattr(dead, 'death_source', None)}")

    poses = _effets_poses_par(fired.get("move_res"))
    nom_1019 = "InescapableDeath_HitsReduction"
    print(f"       effets poses par le move (live) = {sorted(poses)}")

    assert INESCAPABLE_DEATH_HITS_RED not in fired["off_before"], \
        f"1019 deja present dans l'etat offline AVANT le move ({sorted(fired['off_before'])})"
    # NATIF : on tranche par le RETOUR du move. `TurnsUntilUnitOwnerTurn` peut faire expirer 1019
    # avant qu'on relise l'etat (le tour bascule seul), et le canal `IsActive` le masquerait de
    # toute facon -- deux facons de lire un ZERO qui ne prouve rien.
    assert nom_1019 in poses, \
        (f"le natif n'a PAS pose {nom_1019} pendant le kill en overwatch "
         f"(effets poses={sorted(poses)}) -- RE a revoir")
    assert OVERWATCH_AUTO_ATTACK in live_after, \
        (f"1009 perdu apres le kill cote natif (effets={sorted(live_after)}) -- "
         f"`ActivateEffect(Owner, 1009)` du Triggered #1 ne re-arme pas l'overwatch")
    # PORT : meme salve rejouee -> meme pose.
    assert INESCAPABLE_DEATH_HITS_RED in off_after, \
        (f"le port n'a PAS pose 1019 apres le kill en overwatch (effets={sorted(off_after)}) -- "
         f"`EFFECT_TRIGGERS[1018]` manquant, ou son gate refuse a tort")
    assert OVERWATCH_AUTO_ATTACK in off_after, \
        f"1009 perdu cote port apres le kill (effets={sorted(off_after)})"
    # la magnitude du stat-mod : `Negative(HitReductionValue())` = -1 (constante `hitsReduction`).
    assert extra_hits == -1, \
        f"EXTRA_HITS offline={extra_hits}, attendu -1 (= -hitsReduction de `InescapableDeath`)"
