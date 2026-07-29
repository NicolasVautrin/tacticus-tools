"""GARDE live de `CursedPlagueBell_ExtraMove` (EffectType 0x431 = 1073) -- le buff +MOUVEMENT de
l'aura `ContagionsOfNurgle` de `deathBlightbringer` (<< Corrodius >>, POOL-HERO rank 17).

NATIF (build rnca9r7q6c) -- classe d'effet BESPOKE (elle n'utilise PAS la feuille generique
`AddStaticStatModifierEffect`, contrairement a `BlackRage_ExtraMove` / `Waaagh_ExtraMovement`) :

    IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$ApplyInternal
      == ...$$AddStatModifier
      = DSLBehaviors.ChangeStat( Entity(target), Stat(1 = Movement, 5 = Modification), 4 = Modify,
                                 DSLFormulas.Direct(GetNumberConstant(0xe = extraMovement)),
                                 Entity(effect), 1 = OnlyAlive, false, false )
    ...$$RevertInternal == ...$$RevertStatModifier
      = le MEME appel en Stat(1 = Movement, 6 = ResetModification), montant <DSLFormulas+0x18> = Direct(0)

Le VECTEUR (`CursedPlagueBellMovementAbility$$CreateBehaviour` = `AddEffect(0x431, ..., turns = 1)`)
n'est PAS le sujet de ce fichier : il pose l'effet cote NATIF, ici on garde la CLASSE D'EFFET portee
(`engine/entities/effects/loki/cursed_plague_bell.py`) sur un etat SEEDE de cette bataille.

CE QUE CES GARDES INTERDISENT, et qui est SILENCIEUX sans elles :
  * l'attribution du seed retombe dans le residu opaque `CAPTURED_SOURCE` -> la contribution n'est
    plus RETIRABLE, et a l'expiration (l'effet dure UN tour) l'unite garde son +1 Movement A VIE
    offline alors que le natif le retire. Mesure de la mutation (registre sans l'entree 1073,
    `probe_224_cursed_plague_bell_extramove.py --mutate registry`) : `offline MOVEMENT = 4, natif 3`.
  * le gate d'appartenance : le PORTEUR de l'aura est EXCLU de sa propre selection
    (`SurroundingFriends` = anneau) et un ami NON-Chaos ne recoit rien.

Mesure detaillee (attribution, tuiles atteignables, regime hors-aura) :
`probe_224_cursed_plague_bell_extramove.py`.
"""
from __future__ import annotations

import pytest

BELL = "deathBlightbringer"        # Corrodius -- porteur de l'aura ContagionsOfNurgle
CHAOS_ALLIES = ("worldJakhal", "blackAbaddon")
NON_CHAOS_ALLY = "astraBullgryn"   # Imperial -- contre-cas du gate UnitsWithTrait(Chaos)
EXTRA_MOVE = 1073                  # 0x431 CursedPlagueBell_ExtraMove
BUILD = ["--p-units", ",".join((BELL,) + CHAOS_ALLIES + (NON_CHAOS_ALLY,)),
         "--a-units", "necroWarden,necroWarden",
         "--hp-target", "300000", "--hp-player", "300000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _effect_ids(u):
    return {e.get("effectType") for e in (u.get("effects") or [])}


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                            "captureEvents": False}, 60)
    return None, None


def _live_movement(rpc, rid, unit_id):
    """`GetStat(unit, Movement, Current)` natif = `combatSnapshot.units[].stats.movement`."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    for su in (snap.get("units") or []) if isinstance(snap, dict) else []:
        if su.get("entityId") == unit_id:
            return int((su.get("stats") or {}).get("movement") or 0)
    return None


def _live_move_effect_amount(rpc, rid, unit_id):
    """Part de la `ValueModification` de Movement attribuee par le natif a une entite NON-unite
    (= l'entite-effet), + le residu, via `statModSources`."""
    sm = rpc("statModSources", {"runnerId": rid, "unitId": unit_id, "minAbs": 1}, 90)
    for uu in (sm.get("units") or []) if isinstance(sm, dict) else []:
        if uu.get("entityId") != unit_id:
            continue
        mv = (uu.get("mods") or {}).get("movement")
        if not mv:
            return 0, 0
        return (sum(int(s.get("amount") or 0) for s in (mv.get("bySource") or [])
                    if not s.get("sourceIsUnit")),
                int(mv.get("residual") or 0))
    return 0, 0


@pytest.fixture(scope="module")
def bell_battle(live_session, rpc, build_runner):
    """Bataille ou Corrodius pose 1073 sur ses amis Chaos, + l'etat OFFLINE charge de la MEME capture
    (l'effet y est donc SEEDE, pas pose par le moteur porte -- c'est le regime qui casse en silence)."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent

    rid = build_runner("777", extra=BUILD, board="MC1_67")["rid"]
    dec, bell = _advance_to_my_turn(rpc, rid, BELL)
    if bell is None:
        pytest.skip("Corrodius absent / tour non atteint")
    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    carriers = [u for u in (dec0.get("units") or [])
                if u.get("alive") and EXTRA_MOVE in _effect_ids(u)]
    if not carriers:
        pytest.skip("aucun porteur de 1073 sur cette bataille (aura vide)")
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    state = load_state(dec0, ob0, snap0)
    if state.effects is None:
        pytest.skip("etat offline sans effets (snapshot incomplet)")
    ok = [u for u in carriers
          if state.get_entity(u["id"]) is not None
          and state.get_entity(u["id"]).get_component(StatsComponent) is not None
          and state.effects.has_effect(u["id"], effect_type=EXTRA_MOVE)]
    if not ok:
        pytest.skip("1073 non seede offline -> rien a garder ici")
    return {"rid": rid, "dec": dec0, "state": state, "carriers": ok}


def test_cursed_plague_bell_extramove_is_attributed_per_source(bell_battle, rpc):
    """CONDITION NECESSAIRE du revert : la contribution SEEDE vit sous une cle d'effet retirable,
    du MEME montant que celui que le natif attribue a l'entite-effet, residu opaque NUL.

    Le natif rend `movement = {total: 1, residual: 0, bySource: [{source: <entite-effet>, amount: 1,
    sourceIsUnit: false}]}` -- mirror de `Entity(effect)` en `modificationEntity` du `ChangeStat`."""
    from engine.entities.stats import StatType, CAPTURED_SOURCE
    from engine.runner.components import StatsComponent

    rid, state = bell_battle["rid"], bell_battle["state"]
    for u in bell_battle["carriers"]:
        uid = u["id"]
        ctx = state.get_entity(uid).get_component(StatsComponent).ctx
        comp = ctx.stats.components.get(int(StatType.MOVEMENT))
        assert comp is not None, "u%s (%s) : MOVEMENT non seede offline" % (uid, u["visualId"])
        per = dict(comp.modification.per_source)
        keys = [k for k in per if isinstance(k, tuple) and k[:2] == ("statmod", EXTRA_MOVE)]
        live_amt, live_res = _live_move_effect_amount(rpc, rid, uid)
        assert keys, ("u%s (%s) : stat-mod 1073 SEEDE non attribue (per_source=%s) -> son retrait ne "
                      "pourra rien retirer" % (uid, u["visualId"], per))
        assert sum(int(per[k]) for k in keys) == live_amt, \
            ("u%s : montant offline %d != montant natif attribue a l'entite-effet %d"
             % (uid, sum(int(per[k]) for k in keys), live_amt))
        assert int(per.get(CAPTURED_SOURCE, 0)) == 0, \
            ("u%s : residu opaque %d alors que le natif a residual=%d"
             % (uid, int(per.get(CAPTURED_SOURCE, 0)), live_res))


def test_cursed_plague_bell_extramove_gate_excludes_owner_and_non_chaos(bell_battle):
    """Le PORTEUR de l'aura est exclu de sa propre selection (`SurroundingFriends` = anneau autour de
    l'unite, cf. `DestroyTheWitch_ExtraDamage`) et un ami NON-Chaos n'est pas selectionne
    (`UnitsWithTrait(0x7ea = Chaos)`). Garde de MONTAGE : si elle tombe, la mesure du test principal
    ne porte plus sur ce qu'on croit."""
    dec = bell_battle["dec"]
    for vis in (BELL, NON_CHAOS_ALLY):
        u = _find(dec, vis)
        if u is None:
            continue
        assert EXTRA_MOVE not in _effect_ids(u), \
            ("%s porte 1073 : le montage ne discrimine plus le gate "
             "(SurroundingFriends exclut le porteur, UnitsWithTrait(Chaos) exclut l'Imperial)" % vis)


def test_cursed_plague_bell_extramove_reverts_at_expiry_like_live(bell_battle, rpc):
    """LE CRITERE : l'effet dure UN tour ; a son expiration le natif SORT le +1 du stat, le port doit
    faire de meme -- on compare la VALEUR ABSOLUE (le bug est invisible en delta).

    On joue le MEME geste des deux cotes : `endturn` natif / `EndTurnOperation.execute` offline (le
    VRAI foyer porte : tick de duree puis `revert_stat_mods_of_removed_effects`, mirror de
    `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`)."""
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    from engine.runner.operations.turnflow import EndTurnOperation

    rid, state = bell_battle["rid"], bell_battle["state"]
    carriers = bell_battle["carriers"]
    pre = {}
    for u in carriers:
        uid = u["id"]
        ctx = state.get_entity(uid).get_component(StatsComponent).ctx
        live_pre = _live_movement(rpc, rid, uid)
        off_pre = int(ctx.stat(StatType.MOVEMENT))
        assert off_pre == live_pre, \
            "u%s : le seed ne reproduit deja pas GetStat(MOVEMENT) (offline %s != natif %s)" \
            % (uid, off_pre, live_pre)
        pre[uid] = (off_pre, live_pre, ctx)

    assert _ok(rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                                   "captureEvents": False}, 90)), "endturn natif refuse"
    EndTurnOperation.execute(state, advance=False)

    for u in carriers:
        uid = u["id"]
        off_pre, live_pre, ctx = pre[uid]
        live_post = _live_movement(rpc, rid, uid)
        off_post = int(ctx.stat(StatType.MOVEMENT))
        assert not state.effects.has_effect(uid, effect_type=EXTRA_MOVE), \
            "u%s : 1073 (turns=1) non expire offline au tick de fin de tour" % uid
        if live_post == live_pre:
            pytest.skip("u%s : le natif n'a pas fait redescendre MOVEMENT -> rien a garder" % uid)
        assert off_post == live_post, \
            ("u%s (%s) : stat-mod SEEDE non reverte a l'expiration -- offline garde MOVEMENT=%d "
             "alors que le natif est redescendu a %d (ecart +%d conserve a vie)"
             % (uid, u["visualId"], off_post, live_post, off_post - live_post))


def test_cursed_plague_bell_extramove_does_not_drift_over_turns(live_session, rpc, build_runner):
    """PAS DE DERIVE sur plusieurs tours -- la garde de l'ARTICULATION avec le vecteur de pose.

    Depuis que `CursedPlagueBellMovementAbility` est portee (`triggers/loki/cursed_plague_bell.py`),
    l'effet est RE-POSE offline a chaque debut de tour du porteur, sur un etat ou une PREMIERE
    instance est deja SEEDEE. Deux instances distinctes = deux cles de source distinctes : si le
    revert a l'expiration manquait (ou tombait au mauvais tour), le +1 s'EMPILERAIT tour apres tour
    au lieu d'osciller. Le natif, lui, cree bien un `effectId` NEUF a chaque tour et retire le
    precedent -- le MOVEMENT y oscille base <-> base+1, mesure.

    On joue donc TROIS cycles complets des deux cotes (`applyAction endturn` natif /
    `EndTurnOperation.execute(advance=True)` offline, qui enchaine ChangeTurn + StartTurn et
    declenche donc le trigger `On(TurnStart_Other)` du vecteur) et on compare la VALEUR ABSOLUE a
    chaque demi-tour."""
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    from engine.runner.operations.turnflow import EndTurnOperation
    from engine.runner.snapshot import load_state

    rid = build_runner("777", extra=BUILD, board="MC1_67")["rid"]
    dec, bell = _advance_to_my_turn(rpc, rid, BELL)
    if bell is None:
        pytest.skip("Corrodius absent / tour non atteint")
    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    state = load_state(dec0, ob0, snap0)
    carriers = [u["id"] for u in (dec0.get("units") or [])
                if u.get("alive") and EXTRA_MOVE in _effect_ids(u)
                and state.get_entity(u["id"]) is not None
                and state.get_entity(u["id"]).get_component(StatsComponent) is not None]
    if not carriers or state.effects is None:
        pytest.skip("aucun porteur de 1073 exploitable offline")

    def _off(uid):
        ctx = state.get_entity(uid).get_component(StatsComponent).ctx
        comp = ctx.stats.components.get(int(StatType.MOVEMENT))
        per = dict(comp.modification.per_source) if comp is not None else {}
        keys = [k for k in per if isinstance(k, tuple) and k[:2] == ("statmod", EXTRA_MOVE)]
        return int(ctx.stat(StatType.MOVEMENT)), len(keys)

    seen = {uid: [_off(uid)] for uid in carriers}
    live = {uid: [_live_movement(rpc, rid, uid)] for uid in carriers}
    for _ in range(6):                                   # 6 demi-tours = 3 cycles complets
        if not _ok(rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                                       "captureEvents": False}, 90)):
            break
        EndTurnOperation.execute(state, advance=True)
        for uid in carriers:
            seen[uid].append(_off(uid))
            live[uid].append(_live_movement(rpc, rid, uid))

    for uid in carriers:
        offs = [m for m, _ in seen[uid]]
        keys = [k for _, k in seen[uid]]
        print("[no-drift] u%s offline=%s (cles 1073 par tour=%s) ; natif=%s" % (uid, offs, keys, live[uid]))
        assert max(keys) <= 1, \
            ("u%s : %d cles de source 1073 simultanees -> le +1 s'EMPILE (profil offline %s)"
             % (uid, max(keys), offs))
        assert offs == live[uid], \
            ("u%s : derive du MOVEMENT sur les tours -- offline %s, natif %s" % (uid, offs, live[uid]))
