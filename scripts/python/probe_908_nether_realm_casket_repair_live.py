#!/usr/bin/env python
"""Probe #908 volet REPAIR -- `NetherRealmCasket_LivingMetalBonus` (EffectType 0x5b0 = 1456).

CE QUE CE PROBE MESURE, et pourquoi ce regime-la et pas un autre
================================================================
Le descripteur natif est
`IdunBattle.Entities.Effects.Loki.NetherRealmCasket_LivingMetalBonusEffect$$CreateEffectRepairBonus`
= `ForAddition(get_OwnerIsTarget & TriggeringAbilityIs(LivingMetalRepair 0x3f2),
ConfigVar(0x20 = hpToHeal))`. Son gate de CAUSE n'est satisfait que par UN call-site du build : le
trigger du trait `LivingMetal` (`...LivingMetalRepairAbility$$CreateBehaviour`, qui passe
`cause = AbilityOrEffect(LivingMetalRepair)` a `IdunBattleLogic.Entities.DSLBehaviors$$Repair`).
La face DECISION ne peut donc JAMAIS le declencher -- c'est la face COMBAT ou rien.

MONTAGE, et il porte son TEMOIN dans le meme tour
=================================================
  P = [necroDestroyer (RELIQUE equipee, niveau L), necroOverlord (LivingMetal, SANS relique)]
  A = [necroWarden]
  etat force par `--unit-stat` : `Health` = maxHP, `RemainingHealth` = maxHP/2 sur les DEUX.

Les DEUX unites de P portent `LivingMetal`, donc les DEUX regenerent au meme turn-start, dans le
MEME endturn, sur le MEME etat. La seule chose qui les separe est la relique. Le temoin n'est pas
un second run : c'est la meme mesure, ce qui elimine d'un coup le seed, le board, l'ordre des tours
et l'etat de PV comme causes possibles de l'ecart.

  attendu porteur : round_half_even(10% maxHP)  +  hpToHeal[L]
  attendu temoin  : round_half_even(10% maxHP)                  <- le MEME premier terme

⚠ LE CHOIX DES DEUX UNITES EST UNE CONTRAINTE DE MESURE, pas une preference. Les trois porteurs
autorises de la relique sont `necroWarden`, `necroSpyder`, `necroDestroyer` -- et DEUX d'entre eux
REPARENT par ailleurs, ce qui polluerait le delta de PV :
  * `necroSpyder`  -> passif `FabricatorClawArray` (repare un allie Mechanical adjacent) ;
  * `necroWarden`  -> passif `RelentlessMarch` (repare les Mechanical affectes, 1455 PV).
`necroDestroyer` (passif `InescapableDeath`, purement offensif) est le SEUL propre. Cote temoin,
`necroOverlord` est LivingMetal + Mechanical et son passif `MyWillBeDoneOverlord` ne touche pas aux
PV. Mesure de controle du montage initial, AVANT tout endturn : porteur `20000 + 4000 + 1086`,
temoin `20000 + 4000` -- l'ecart EST le bonus, des le premier turn-start.

L'etat de depart est POSE, pas obtenu en frappant : une phase d'attaque laissait le temoin INTACT
(l'IA ne ciblait qu'une unite), donc `missing == 0` et une regen capee -- regime non discriminant.

TROIS BRAS OFFLINE sur le MEME etat capture (aucun rejeu, aucun RNG -- la reparation n'en tire pas)
==================================================================================================
  PORT      : le port courant. Doit egaler le LIVE, EXACTEMENT, pour les DEUX unites.
  NOCAUSE   : `ability_or_effect` force a `None` a l'entree du modifier -- la vue « d'AVANT #908 »,
              ou la cause etait CONSTRUITE par le natif et JETEE par le port. Doit rendre le seul
              10 %, donc DIVERGER du live sur le porteur et l'EGALER sur le temoin.
  PASSIF    : `triggered_ability_state` neutralise -- la vue « sans le canal #357 ». Le foyer
              retombe alors sur le `level` de l'EFFET CAPTE (`decisionView.units[].effects[].level`),
              qui n'a AUCUN rapport avec le niveau de la relique. MESURE : il vaut 1, donc le port
              lit `hpToHeal[1] = 980` la ou le natif lit `hpToHeal[3] = 1086`.
              ⚠ La 1re redaction de ce bras annoncait « le port lit `ability_level` (50) -> dernier
              palier 1456 » : FAUX pour CE chemin. `ability_level` est ce que lisent les classes
              d'EFFET (canal crit), pas ce foyer-ci, qui n'a que le dict `{name, level, source}`.
              Le mutant mord dans les deux lectures, mais seule la seconde est la vraie.

NOCAUSE et PASSIF sont les MUTANTS : s'ils passent tous les deux, c'est le TEMOIN qui est aveugle
(cible saturee, bonus non discriminant), et le probe le dit au lieu de rendre PASS.

ASCII only (cp1252).
Usage: python probe_908_nether_realm_casket_repair_live.py [--seed 20304] [--hp 40000] [--level 3]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from engine.runner import snapshot as SNAP                                # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402
from engine.runner.operations import repair as RP                         # noqa: E402
from engine.runner.operations.triggers.dispatch.turn import turn_start_other_triggers  # noqa: E402
from engine.runner.operations.triggers.loki.living_metal import (         # noqa: E402
    living_metal_pct, _round_half_even)
from engine.entities.effects.loki import nether_realm_casket as NRC       # noqa: E402

#: PORTEUR : le seul des trois `allowedUnits` de la relique qui ne repare rien par ailleurs.
PORTEUR = "necroDestroyer"
#: TEMOIN : `LivingMetal` + `Mechanical`, passif sans effet sur les PV.
TEMOIN = "necroOverlord"
ADVERSE = "necroWarden"
ROOT = PYDIR.parents[1]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def hp_to_heal(level: int) -> int:
    """`ConfigVar(0x20 = hpToHeal)` au niveau de RELIQUE demande, relu du gameconfig VIVANT.

    Jamais un scalaire en dur : c'est la table `abilities.NetherRealmCasket.variables.hpToHeal`
    (10 paliers), indexee par `Idun.Shared.Level$$ToZeroBasedIndex` puis clampee au dernier."""
    from engine.entities.effects.magnitude import ability_var as _av
    v = _av(NRC.ABILITY_ID, NRC.VAR_HP_TO_HEAL, level, multiplier_pct=100)
    return int(v) if v is not None else 0


def build(state_path: Path, seed: int, hp: int, level: int, board: str, relique: bool = True):
    """Monte le runner et POSE l'etat de PV (`Health` = maxHP, `RemainingHealth` = maxHP/2).

    `relique = False` = le bras SANS relique du meme porteur : c'est le TEMOIN INTER-RUN, celui qui
    montre que l'ecart vient de la relique et pas du choix d'unite."""
    state_path.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_path), "--board", board,
           "--p-units", "%s,%s" % (PORTEUR, TEMOIN), "--a-units", ADVERSE,
           "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (PORTEUR, hp, hp // 2),
           "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (TEMOIN, hp, hp // 2)]
    if relique:
        cmd += ["--equip-relic", "%s:%s:%d" % (PORTEUR, NRC.ABILITY_ID, level)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_path.exists():
        print("[908] build KO:", (proc.stderr or proc.stdout or "")[-600:], file=sys.stderr)
        sys.exit(2)
    return json.loads(state_path.read_text())["runnerId"]


def snap_hp(sid, rid):
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return {u.get("entityId"): (int((u.get("stats") or {}).get("health") or 0),
                                int(u.get("healthMax") or 0)) for u in (snap.get("units") or [])}


def cp(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")


def alive_units(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    return cp(sid, rid)


def regen_offline(dec, ob, snap, player, bras: str) -> dict:
    """Rejeu OFFLINE du turn-start de `player` sur l'etat capture, sous l'un des trois bras.

    Les deux mutations sont posees AVANT `load_state` quand elles doivent l'etre, et restaurees en
    `finally`. Elles portent sur le FOYER (`repair._repair_modifier` / `triggered_ability_state`),
    pas sur la classe d'effet : c'est ce qui garantit qu'elles mordent quel que soit le chemin."""
    import engine.runner.operations.triggers.base as TB
    saved_mod, saved_state = RP._repair_modifier, TB.triggered_ability_state
    try:
        if bras == "NOCAUSE":
            # la vue d'AVANT #908 : la cause est JETEE avant d'atteindre le modifier.
            def _no_cause(state, target_id, ability_or_effect=None):
                return saved_mod(state, target_id, ability_or_effect=None)
            RP._repair_modifier = _no_cause
        elif bras == "PASSIF":
            # la vue sans le canal #357 : le foyer retombe sur le `level` de l'EFFET CAPTE, qui
            # n'indexe PAS la table de la relique (mesure : 1 -> `hpToHeal[1] = 980`).
            TB.triggered_ability_state = lambda st, uid, name: (None, None)
        state = load_state(dec, ob, snap)
        res = turn_start_other_triggers(state, player)
        return {r.get("unit"): r for r in res if r.get("type") == "living_metal_repair"}
    finally:
        RP._repair_modifier, TB.triggered_ability_state = saved_mod, saved_state


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20304)
    ap.add_argument("--hp", type=int, default=40000)
    ap.add_argument("--level", type=int, default=3, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args(argv)

    sf = Path(a.state_file) if a.state_file else (ROOT / "logs" / "runners" / "_908_nrc_repair.json")
    sf.parent.mkdir(parents=True, exist_ok=True)

    sid = _resolve_session()

    def rpc(method, body=None, timeout=60):
        return (_rpc(sid, method, [body] if body is not None else [], timeout=timeout)
                .get("result") or {})

    # CANAL RELIQUE (#357/#363) : sans transport ambiant lie, `UnitContext.tertiary_ability` reste
    # `None` et le port lit le couple PASSIF -- c'est-a-dire exactement le bras PASSIF, en silence.
    SNAP.bind_live_rpc(rpc)

    pct = living_metal_pct()
    base = _round_half_even(a.hp * pct / 100)
    bonus = hp_to_heal(a.level)
    bonus_dernier = hp_to_heal(10)
    print("[908] seed=%d hp=%d pct=%d%% base_regen=%d relique_niveau=%d hpToHeal=%d "
          "(dernier palier=%d)" % (a.seed, a.hp, pct, base, a.level, bonus, bonus_dernier))
    if bonus <= 0:
        print("[908] REGIME NON DISCRIMINANT : hpToHeal[%d] = 0" % a.level)
        return 4
    if bonus == bonus_dernier:
        print("[908] ATTENTION : niveau %d == dernier palier -> le bras PASSIF ne peut PAS "
              "diverger. Choisir --level != 10 pour armer ce mutant." % a.level)

    rid = build(sf, a.seed, a.hp, a.level, a.board)
    print("[908] runner=%s" % rid)
    ok, notes = True, []
    try:
        al = alive_units(sid, rid)
        spy = next((u for u in al if u.get("visualId") == PORTEUR and u.get("team") == 1), None)
        war = next((u for u in al if u.get("visualId") == TEMOIN and u.get("team") == 1), None)
        if not spy or not war:
            teams = [(u.get("visualId"), u.get("team")) for u in al]
            print("[908] roster KO : %r" % (teams,))
            return 2
        sid_u, wid_u = spy["id"], war["id"]
        p_team = cp(sid, rid)
        print("[908] porteur=u%s (%s, relique niv %d) temoin=u%s (%s, sans relique) player=%s"
              % (sid_u, PORTEUR, a.level, wid_u, TEMOIN, p_team))

        # L'etat est POSE, pas obtenu en frappant. On verifie seulement qu'il RESTE de la place
        # pour la regen COMPLETE -- sinon `MaxFillUp` caperait et le bonus serait invisible.
        besoin = base + bonus
        hp0 = snap_hp(sid, rid)
        for uid, nom in ((sid_u, "porteur"), (wid_u, "temoin")):
            h = hp0.get(uid)
            if h is None:
                print("[908] %s absent du snapshot" % nom)
                return 2
            if (h[1] - h[0]) <= besoin:
                print("[908] %s a missing=%d <= %d -> REGIME NON DISCRIMINANT (regen capee)"
                      % (nom, h[1] - h[0], besoin))
                return 4
        print("[908] etat pose : porteur=%s (missing %d) | temoin=%s (missing %d)"
              % (hp0[sid_u], hp0[sid_u][1] - hp0[sid_u][0],
                 hp0[wid_u], hp0[wid_u][1] - hp0[wid_u][0]))

        cur = cp(sid, rid)
        if cur == p_team:
            cur = endturn(sid, rid)          # amener le tour ENNEMI : le prochain endturn regen P
        print("[908] capture S au tour ENNEMI cp=%s" % cur)

        dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        before = snap_hp(sid, rid)

        # verifier que le natif a bien POSE l'effet sur le porteur, et PAS sur le temoin.
        eff_par_unite = {}
        for u in (dec.get("units") or []):
            eff_par_unite[u.get("id")] = sorted(
                str(e.get("name")) for e in (u.get("effects") or []))
        print("[908] effets NATIFS porteur u%s : %r" % (sid_u, eff_par_unite.get(sid_u)))
        print("[908] effets NATIFS temoin  u%s : %r" % (wid_u, eff_par_unite.get(wid_u)))
        if NRC.LIVING_METAL_BONUS_EFFECT_NAME not in (eff_par_unite.get(sid_u) or []):
            print("[908] ** FAIL montage ** : le natif n'a PAS pose 1456 sur le porteur")
            return 3
        if NRC.LIVING_METAL_BONUS_EFFECT_NAME in (eff_par_unite.get(wid_u) or []):
            print("[908] ** FAIL montage ** : le TEMOIN porte 1456 -- il n'est plus un temoin")
            return 3

        # LIVE : endturn -> turn-start de P -> LivingMetal des DEUX unites.
        newcp = endturn(sid, rid)
        after = snap_hp(sid, rid)
        live_spy = after[sid_u][0] - before[sid_u][0]
        live_war = after[wid_u][0] - before[wid_u][0]
        print("[908] LIVE endturn -> cp=%s | porteur +%d | temoin +%d"
              % (newcp, live_spy, live_war))

        # OFFLINE : les trois bras, sur le MEME etat capture.
        bras = {}
        for nom in ("PORT", "NOCAUSE", "PASSIF"):
            r = regen_offline(dec, ob, snap, p_team, nom)
            bras[nom] = (int((r.get(sid_u) or {}).get("repaired") or 0),
                         int((r.get(wid_u) or {}).get("repaired") or 0))
            print("[908] OFFLINE %-8s porteur=%d temoin=%d" % (nom, bras[nom][0], bras[nom][1]))

        # === verdicts ===
        attendu_porteur = base + bonus
        if bras["PORT"][0] != live_spy:
            print("[908] ** FAIL porteur ** port=%d != live=%d" % (bras["PORT"][0], live_spy))
            ok = False
        if bras["PORT"][1] != live_war:
            print("[908] ** FAIL temoin ** port=%d != live=%d" % (bras["PORT"][1], live_war))
            ok = False
        if live_spy != attendu_porteur:
            print("[908] ** FAIL formule ** live porteur=%d != 10%%(%d) + hpToHeal[%d](%d) = %d"
                  % (live_spy, base, a.level, bonus, attendu_porteur))
            ok = False
        if live_war != base:
            print("[908] ** FAIL temoin/formule ** live temoin=%d != 10%%(%d)" % (live_war, base))
            ok = False

        # --- les MUTANTS : un mutant VERT dit que le temoin est aveugle ---
        if bras["NOCAUSE"][0] == live_spy:
            print("[908] ** MUTANT VERT (NOCAUSE) ** : jeter la cause ne change RIEN sur le "
                  "porteur -> ce bras ne prouve pas le canal (cible saturee ? bonus nul ?)")
            ok = False
        else:
            notes.append("NOCAUSE mord : %d != live %d (ecart %d = hpToHeal)"
                         % (bras["NOCAUSE"][0], live_spy, live_spy - bras["NOCAUSE"][0]))
        if bras["NOCAUSE"][1] != live_war:
            print("[908] ** FAIL ** : NOCAUSE change le TEMOIN (%d != %d) -- effet de bord"
                  % (bras["NOCAUSE"][1], live_war))
            ok = False
        if bonus != bonus_dernier:
            if bras["PASSIF"][0] == live_spy:
                print("[908] ** MUTANT VERT (PASSIF) ** : neutraliser le canal #357 ne change "
                      "RIEN -> le niveau TERTIAIRE n'est pas ce qui est lu")
                ok = False
            else:
                notes.append("PASSIF mord : %d != live %d (sans le canal #357 le foyer indexe "
                             "`hpToHeal` par le level de l'EFFET, pas par celui de la relique)"
                             % (bras["PASSIF"][0], live_spy))

        for n in notes:
            print("[908] contre-epreuve OK -- %s" % n)
        print("[908] BILAN porteur live=%d port=%d attendu=%d(base %d + bonus %d) | "
              "temoin live=%d port=%d attendu=%d -> %s"
              % (live_spy, bras["PORT"][0], attendu_porteur, base, bonus,
                 live_war, bras["PORT"][1], base, "OK" if ok else "** FAIL **"))
        return 0 if ok else 1
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print("[908] runner %s dispose" % rid)
        except Exception as e:
            print("[908] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
