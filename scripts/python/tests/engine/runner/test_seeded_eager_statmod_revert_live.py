"""R16 -- GARDE : un stat-mod EAGER present AU SEED redescend-il quand son effet part, comme en live ?

Le symptome que ce fichier garde est SILENCIEUX : le buff est bien APPLIQUE (il est cuit dans le
`Current` capte), il ne REDESCEND simplement jamais. Aucun test mesurant un DELTA (pose fraiche moins
etat courant) ne peut le voir -- c'est exactement pourquoi `test_doctrina_imperatives_live.py` passait
avec le bug. Ici on mesure la VALEUR ABSOLUE apres retrait, confrontee au natif.

NATIF (build gqfc5mff6c) : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` emet
`ChangeStat(Entity(target), Position(stat, part 5|9), 4, Direct(amount), Entity(<effectEntity>))` et
`IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` REJOUE le meme appel en
`Position(stat, part 6)` avec LA MEME `Entity(<effectEntity>)` ->
`IdunBattle.Entities.Components.ValueModification$$ReverseModification`. La source EST l'entite-effet :
elle part avec l'effet, INCONDITIONNELLEMENT, quel que soit le chemin qui l'a posee. Le port
distinguait « pose en jeu » (cle `stat_mod_source`) de « present au seed » (aucune cle, contribution
noyee dans le residu opaque `CAPTURED_SOURCE`) -- ce dernier n'etait donc pas retirable.

PORTEUR : `ProtectorImperative` (0x4df=1247) de `DoctrinaImperatives` (admecMarshall / Tan Gi'da) --
+extraArmor sur **FixedArmor(16)**, pose PAR DEFAUT au debut de bataille par
`IdunBattleLogic.Entities.Abilities.Active.Loki.DoctrinaImperatives_SetStart$$CreateBehaviour`, donc
DEJA PRESENT dans toute capture (= SEEDE par construction), et retire par le TOGGLE
`IdunBattleLogic.Entities.Abilities.Active.Loki.DoctrinaImperativesAbility$$ExecuteBehaviour`
(`If(HasEffect(1247), THEN AddEffect(1248) + RemoveEffect(1247), ELSE ...)`). C'est le seul porteur du
pool ou le meme geste est jouable des DEUX cotes (live et offline) sur un etat SEEDE.

Mesure OFFLINE pure equivalente (les deux formes, mono-stat et multi-stat) :
`probe_r16_eager_statmod_revert.py`.
"""
from __future__ import annotations

import pytest

TAN_VIS = "admecMarshall"        # Tan Gi'da
ALLY_VIS = "admecRuststalker"    # Exitor-Rho (Mechanical)
ABILITY = 1118                   # DoctrinaImperatives
PROTECTOR = 1247                 # ProtectorImperative (+extraArmor sur FixedArmor)
CONQUEROR = 1248                 # ConquerorImperative
BUILD = ["--roster", "1", "--p-units", f"{TAN_VIS},{ALLY_VIS}",
         "--a-units", "necroWarden,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _effect_ids(u):
    return {e.get("effectType") for e in (u.get("effects") or [])}


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _advance_to_my_turn(rpc, rid, vis, max_iter=20):
    """Avance jusqu'au tour du proprietaire de `vis`. Renvoie (dec, unit) ou (None, None)."""
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


def _live_fixed_armor(rpc, rid, unit_id):
    """`GetStat(unit, FixedArmor, Current)` cote NATIF = `combatSnapshot.units[].stats.fixedArmor`."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    for su in (snap.get("units") or []) if isinstance(snap, dict) else []:
        if su.get("entityId") == unit_id:
            return int((su.get("stats") or {}).get("fixedArmor") or 0), snap
    return None, snap


def _setup(rpc, build_runner, seed="777", board="MC1_67"):
    """Runner + Tan Gi'da a son tour avec `ProtectorImperative` (1247) ACTIF (SetStart), et l'etat
    OFFLINE charge depuis la MEME capture (le 1247 y est donc SEEDE, pas pose par le moteur porte).
    Le runner est construit DANS LE TEST -> libere avec lui (discipline « au fil de l'eau »)."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent

    rid = build_runner(seed, extra=BUILD + ["--board", board])["rid"]
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip("Protector(1247) non actif pre-cast (SetStart) -> pas d'etat SEEDE a mesurer")

    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    state = load_state(dec0, ob0, snap0)
    ent = state.get_entity(tan_id)
    if ent is None or ent.get_component(StatsComponent) is None or state.effects is None:
        pytest.skip("Tan Gi'da sans StatsComponent/effects offline (snapshot incomplet)")
    if not state.effects.has_effect(tan_id, effect_type=PROTECTOR):
        pytest.skip("Protector(1247) non seede dans l'etat offline -> rien a garder ici")
    return {"rid": rid, "tan_id": tan_id, "state": state,
            "ctx": ent.get_component(StatsComponent).ctx}


def test_seeded_protector_statmod_is_attributed_per_source(live_session, rpc, build_runner):
    """L'attribution du SEED doit etre PAR-SOURCE, pas opaque -- c'est la condition necessaire du revert.

    ORACLE NATIF : `statModSources` rend la `ValueModification` de FixedArmor ventilee par entite
    source ; pour Tan Gi'da elle porte UNE entree effet-source (l'entite-effet Protector) et
    `residual = 0`. La garde confronte les DEUX bouts : (a) offline la contribution vit sous une cle
    d'effet (`('statmod', 1247, ...)`), PAS sous `CAPTURED_SOURCE` ; (b) son montant == le montant
    natif attribue a l'entite-effet."""
    from engine.entities.stats import StatType, CAPTURED_SOURCE

    live = _setup(rpc, build_runner)
    rid, tan_id, ctx = live["rid"], live["tan_id"], live["ctx"]
    comp = ctx.stats.components.get(int(StatType.FIXED_ARMOR))
    assert comp is not None, "FixedArmor non seede offline"
    per_source = dict(comp.modification.per_source)

    sm = rpc("statModSources", {"runnerId": rid, "unitId": tan_id, "minAbs": 1}, 90)
    live_effect_amt = 0
    for uu in (sm.get("units") or []) if isinstance(sm, dict) else []:
        fa = (uu.get("mods") or {}).get("fixedArmor")
        if not fa:
            continue
        for s in (fa.get("bySource") or []):
            if not s.get("sourceIsUnit") and (s.get("amount") or 0) > 0:
                live_effect_amt = max(live_effect_amt, int(s["amount"]))
    if live_effect_amt <= 0:
        pytest.skip(f"aucun mod FixedArmor effet-source cote natif (sm={str(sm)[:200]})")

    statmod_keys = [k for k in per_source
                    if isinstance(k, tuple) and k[:2] == ("statmod", PROTECTOR)]
    print("[R16 attribution] per_source offline = %s ; natif effet-source = +%d"
          % (per_source, live_effect_amt))
    assert statmod_keys, \
        ("le stat-mod EAGER seede n'est PAS attribue a une source retirable "
         "(per_source=%s) -> son retrait ne pourra rien retirer" % (per_source,))
    off_amt = sum(int(per_source[k]) for k in statmod_keys)
    assert off_amt == live_effect_amt, \
        ("montant attribue offline %d != montant natif attribue a l'entite-effet %d"
         % (off_amt, live_effect_amt))
    assert int(per_source.get(CAPTURED_SOURCE, 0)) == 0, \
        ("residu opaque non nul (%d) alors que le natif attribue tout a l'entite-effet"
         % int(per_source.get(CAPTURED_SOURCE, 0)))


@pytest.mark.parametrize("seed,board", [("777", "MC1_67"), ("31337", "C4_09")])
def test_seeded_protector_statmod_reverts_like_live(live_session, rpc, build_runner, seed, board):
    """LE CRITERE R16 : apres le retrait de l'effet, `GetStat(FixedArmor)` OFFLINE == la valeur NATIVE.

    On joue le MEME geste des deux cotes -- le toggle `DoctrinaImperatives`, qui fait `RemoveEffect(1247)`
    -- et on compare la valeur ABSOLUE (pas un delta : le bug est precisement invisible en delta).
    AVANT le fix R16 : le natif redescend a sa valeur de base, l'offline garde le buff A VIE.

    DEUX couples (board, seed) : la mecanique n'est pas geometrique (stat-mod self), mais un seul
    couple ne distingue pas un invariant d'un artefact de bataille -- deploiement, niveau d'ability
    et multiplier different d'un build a l'autre, donc la magnitude aussi."""
    from engine.entities.stats import StatType
    from engine.runner.abilities.loki import DoctrinaImperativesAbility

    live = _setup(rpc, build_runner, seed=seed, board=board)
    rid, tan_id = live["rid"], live["tan_id"]
    state, ctx = live["state"], live["ctx"]

    live_pre, _ = _live_fixed_armor(rpc, rid, tan_id)
    off_pre = int(ctx.stat(StatType.FIXED_ARMOR) or 0)
    if live_pre is None:
        pytest.skip("FixedArmor natif illisible (combatSnapshot)")
    assert off_pre == live_pre, \
        "le seed ne reproduit deja pas GetStat(FixedArmor) : offline %d != natif %d" % (off_pre, live_pre)

    # LIVE : toggle -> RemoveEffect(1247) -> la ValueModification de l'entite-effet sort du stat.
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": tan_id, "targetId": tan_id, "abilityType": ABILITY}}, 90)
    if not _ok(res):
        pytest.skip("cast 1118 non applique (gate/tour) : %s" % str(res)[:200])
    dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    tan1 = _find(dec1, TAN_VIS)
    assert tan1 is not None and PROTECTOR not in _effect_ids(tan1), \
        "Protector(1247) toujours present cote natif apres le toggle -> mesure invalide"
    live_post, _ = _live_fixed_armor(rpc, rid, tan_id)

    # OFFLINE : le MEME geste sur l'etat SEEDE.
    DoctrinaImperativesAbility().execute_behaviour(state, tan_id, tan_id)
    assert not state.effects.has_effect(tan_id, effect_type=PROTECTOR), \
        "toggle offline : Protector(1247) non retire"
    off_post = int(ctx.stat(StatType.FIXED_ARMOR) or 0)

    print("[R16 revert] FixedArmor natif %d -> %d (-%d) ; offline %d -> %d (-%d)"
          % (live_pre, live_post, live_pre - live_post, off_pre, off_post, off_pre - off_post))
    assert live_post < live_pre, \
        ("le natif n'a pas fait redescendre FixedArmor (%d -> %d) -> rien a garder sur cette bataille"
         % (live_pre, live_post))
    assert off_post == live_post, \
        ("stat-mod EAGER SEEDE non reverte : offline garde FixedArmor=%d apres le retrait de "
         "Protector(1247), le natif est redescendu a %d (ecart +%d conserve a vie)"
         % (off_post, live_post, off_post - live_post))

    # CONTRE-EPREUVE (accumulation) : le retrait ne doit pas seulement « faire baisser », il doit
    # rendre la RE-POSE idempotente. On rejoue le toggle -> Protector FRAICHEMENT pose (cle de POSE,
    # `AddEffectOperation._apply_stat_mods`) : la valeur doit revenir EXACTEMENT a celle que le natif
    # donnait avec Protector actif (`live_pre`), pas s'empiler par-dessus le buff seede. Sans le
    # revert, cette valeur derivait de +extraArmor a CHAQUE aller-retour du toggle.
    DoctrinaImperativesAbility().execute_behaviour(state, tan_id, tan_id)
    assert state.effects.has_effect(tan_id, effect_type=PROTECTOR), \
        "toggle offline #2 : Protector(1247) non re-pose"
    off_again = int(ctx.stat(StatType.FIXED_ARMOR) or 0)
    print("[R16 re-pose] FixedArmor offline apres re-pose de Protector = %d (natif avec Protector : %d)"
          % (off_again, live_pre))
    assert off_again == live_pre, \
        ("accumulation : Protector re-pose donne FixedArmor=%d, le natif avec Protector actif donne %d "
         "(+%d empiles)" % (off_again, live_pre, off_again - live_pre))
