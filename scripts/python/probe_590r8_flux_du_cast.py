"""#590-r8 -- POURQUOI l'attaque commandee de `1101 AttemptedPossession` n'aboutit pas DANS LE
FLUX DU CAST, alors que le MEME corps appele hors cast frappe pour 8252.

CE QUE `#590-r8` A DEJA ETABLI, et qu'on ne re-mesure pas : tout ce qui est AU-DESSUS du corps
`perform_ai_ability_unit_behaviour` est JUSTE (`GetPreferredAttackTarget` rend la cible que le
natif frappe, le moteur d'utilite decide juste, le `range_gate` passe, le corps appele
directement rend `{target: 83, total: 8252}`). L'ecart est STRICTEMENT entre << ce corps appele
depuis `PerformAIAbility.execute` PENDANT le cast >> et << hors cast >>.

CE PROBE NE FITTE RIEN : il INSTRUMENTE le flux reel du cast et imprime, ETAGE PAR ETAGE, ce que
chaque fonction voit en ENTREE et rend en SORTIE, jusqu'au PREMIER etage ou le flux du cast
diverge du meme etage hors cast. Les deux colonnes sont produites par le MEME montage, sur la
MEME copie d'etat, a la MEME graine de MT -- sinon l'ecart mesure serait celui du montage.

Etages traces (dans l'ordre du corps) :
  [A] `PerformAIAbility.execute`               -- units / utility_entity / move_amount / allowed
  [B] `perform_ai_ability_unit_behaviour`      -- _here / _eligible_here / ability_type
  [C] `ai_control_execute_ability_action_for`  -- l'action DECIDEE
  [D] `_apply_move_message`                    -- le deplacement applique
  [E] `_in_attack_range` (post-move)           -- le double filet
  [F] `AttackDamageOperation.execute`          -- le degat

Montage : celui de `probe_590_attempted_possession.py`, reutilise TEL QUEL (meme board MC1_67,
meme seed, memes positions FORCEES) -- une geometrie qui differe ferait mesurer autre chose.

Sortie ASCII stricte. Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_590r8_flux_du_cast.py [--state-name <nom>]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys

import probe_590_attempted_possession as P590

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12 / #486-r15).
DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Il instrumente le flux REEL du cast de 1101 sur un runner live : il depend de tout "
              "le port de l'ability (arbre + effets + PerformAIAbility + le corps partage "
              "perform_ai_ability_unit_behaviour + le moteur d'utilite offline) ET du build "
              "charge, puisque l'etat de depart vient du jeu.",
}


class Trace:
    """Collecteur d'etages. Un `dict` par appel, dans l'ordre chronologique."""

    def __init__(self):
        self.lignes = []

    def note(self, etage: str, **kv):
        self.lignes.append({"etage": etage, **kv})

    def de(self, etage: str):
        return [l for l in self.lignes if l["etage"] == etage]


def _instrumenter(tr: Trace):
    """Pose les sondes et rend la fonction qui les retire.

    Les points d'ancrage sont choisis pour MORDRE (cf. la regle FORME A/B/C du CLAUDE.md) :
      * `perform_ai_ability_unit_behaviour` est importe en FORME C par `PerformAIAbility.execute`
        (`from ..loki.summon import ...` DANS la fonction), donc un `setattr` sur le module
        `loki.summon` est relu a chaque appel ;
      * `ai_control_execute_ability_action_for` est lie en FORME A au niveau module de
        `loki/summon.py` -> on patche le binding DE CE MODULE-LA, pas celui de `summon_ai` ;
      * `_in_attack_range` est importe en FORME C dans le corps -> on patche `triggers.base`.
    """
    import engine.runner.abilities.loki.summon as S
    import engine.runner.operations.triggers.base as TB
    import engine.runner.abilities.targeting as TG
    from engine.runner.operations.damage import AttackDamageOperation

    _vrai_corps = S.perform_ai_ability_unit_behaviour
    _vrai_ia = S.ai_control_execute_ability_action_for
    _vrai_range = TB._in_attack_range
    _vrai_valid = TG.valid_normal_attack_targets
    _vrai_move = S._apply_move_message
    _vrai_atk = AttackDamageOperation.execute

    def corps(state, unit_id, allow_move_action, move_amount, allowed_targets=None,
              ability_type=None):
        tr.note("B", unit=int(unit_id), allow_move_action=bool(allow_move_action),
                move_amount=move_amount,
                allowed_targets=(sorted(allowed_targets) if allowed_targets is not None else None),
                ability_type=ability_type)
        out = _vrai_corps(state, unit_id, allow_move_action, move_amount,
                          allowed_targets=allowed_targets, ability_type=ability_type)
        tr.note("B-out", unit=int(unit_id), retour=out)
        return out

    def ia(state, uid, ability_id, allow_only_move=False, move_amount=None, range_gate=None):
        vus = []

        def gate(t, tile):
            ok = range_gate(t, tile) if range_gate is not None else True
            if len(vus) < 12:
                tid = t.get("id") if isinstance(t, dict) else t
                vus.append((tid, tuple(tile) if tile is not None else None, bool(ok)))
            return ok
        out = _vrai_ia(state, uid, ability_id, allow_only_move=allow_only_move,
                       move_amount=move_amount, range_gate=(gate if range_gate is not None else None))
        tr.note("C", unit=int(uid), ability_id=int(ability_id), move_amount=move_amount,
                action=out, gate_vus=vus)
        return out

    def rng(state, unit_id, target, from_pos=None):
        out = _vrai_range(state, unit_id, target, from_pos=from_pos)
        tr.note("E", unit=int(unit_id),
                target=(target.get("id") if isinstance(target, dict) else target),
                from_pos=(tuple(from_pos) if from_pos is not None else None), ok=bool(out))
        return out

    def valid(state, unit_id, *a, **k):
        out = _vrai_valid(state, unit_id, *a, **k)
        tr.note("B-valid", unit=int(unit_id),
                cibles=sorted(int(x) for x in (out or ())))
        return out

    def move(state, unit_id, to, origin):
        out = _vrai_move(state, unit_id, to, origin)
        tr.note("D", unit=int(unit_id), to=(tuple(to) if to is not None else None),
                origin=(tuple(origin) if origin is not None else None), moved=out)
        return out

    @staticmethod
    def atk(state, attacker_id, target_id, *a, **k):
        out = _vrai_atk(state, attacker_id, target_id, *a, **k)
        tr.note("F", attacker=int(attacker_id), target=int(target_id),
                total=(out or {}).get("total") if isinstance(out, dict) else out)
        return out

    S.perform_ai_ability_unit_behaviour = corps
    S.ai_control_execute_ability_action_for = ia
    TB._in_attack_range = rng
    TG.valid_normal_attack_targets = valid
    S._apply_move_message = move
    AttackDamageOperation.execute = atk

    def retirer():
        S.perform_ai_ability_unit_behaviour = _vrai_corps
        S.ai_control_execute_ability_action_for = _vrai_ia
        TB._in_attack_range = _vrai_range
        TG.valid_normal_attack_targets = _vrai_valid
        S._apply_move_message = _vrai_move
        AttackDamageOperation.execute = _vrai_atk
    return retirer


def _instrumenter_G(tr: Trace, state, caster_id: int):
    """Sonde [G] : le noeud de MONTANT de l'`AddStatOverrideEffect`, DECOMPOSE.

    C'EST L'ETAGE OU #590-r8 SE JOUE, et il fallait le decomposer pour le voir : les trois
    sous-noeuds (`StatAmount(Subject, ATTACK, INITIAL)` / `PercentageOf(dmgPct)` / `Min(maxDmg)`)
    ne se distinguent pas d'un montant global.

    ⚠ **LE SUJET DOIT ETRE LIE AVANT D'EVALUER**, sinon la sonde MESURE SON PROPRE ARTEFACT : la
    feuille fait `replace(entities, subject=u)` par unite (mirror de `param_3[4] = current`) ;
    evaluer sur l'`entities` NU rend `Subject() = None` et 0 PARTOUT -- ce qui imite exactement le
    bug cherche. Premier jet de cette sonde, corrige apres l'avoir vu.

    ⚠ **`ConfigVar` EST EVALUEE ICI POUR MEMOIRE, et son 0 est LE FAIT** : `ctx.config` n'est pas
    branche par `entities_from_state`, donc les deux variables de l'override rendaient 0. Le port
    livre passe par `attempted_possession_damage_vars` (resolution par le foyer
    `active_ability_state` + `ability_var`), donc les deux colonnes sont imprimees cote a cote."""
    from engine.runner.abilities.behaviours.stats import AddStatOverrideEffect
    import engine.runner.abilities.loki.attempted_possession as AP
    from engine.entities.formulas import ConfigVar, PercentageOf, StatAmount
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.entities.selectors.accessors import Subject
    from engine.entities.stats import StatPart, StatType
    _vrai = AddStatOverrideEffect.execute
    _vars = AP.attempted_possession_damage_vars(state, int(caster_id))

    def execute(self, entities, ectx):
        from dataclasses import replace
        from engine.dsl.base import _units_of
        etages = {}
        try:
            for u in _units_of(self.unit_sel, entities):
                sub = replace(entities, subject=u)
                base = StatAmount(Subject(), int(StatType.ATTACK), int(StatPart.INITIAL))
                etages[str(u.get("id") if isinstance(u, dict) else u)] = {
                    "Subject()": (lambda s: s.get("id") if isinstance(s, dict) else repr(s)[:40])(
                        Subject().evaluate(sub)),
                    "StatAmount(ATTACK,INITIAL)": base.evaluate(sub),
                    "StatAmount(ATTACK,CURRENT)": StatAmount(
                        Subject(), int(StatType.ATTACK), int(StatPart.CURRENT)).evaluate(sub),
                    "ConfigVar(dmgPct) [non branchee]":
                        ConfigVar(AbilityVariableType.dmgPct.name).evaluate(sub),
                    "ConfigVar(maxDmg) [non branchee]":
                        ConfigVar(AbilityVariableType.maxDmg.name).evaluate(sub),
                    "PercentageOf via ConfigVar": PercentageOf(
                        ConfigVar(AbilityVariableType.dmgPct.name), base).evaluate(sub),
                    "vars RESOLUES (maxDmg, dmgPct)": list(_vars),
                    "montant du port LIVRE":
                        AP.attempted_possession_damage(*_vars).evaluate(sub),
                    "ctx.config branche": (getattr(sub, "config", None) is not None),
                }
        except Exception as exc:
            etages["EXC"] = "%s:%s" % (type(exc).__name__, exc)
        tr.note("G", stat_type=getattr(self, "stat_type", None), etages=etages)
        return _vrai(self, entities, ectx)
    AddStatOverrideEffect.execute = execute

    def retirer():
        AddStatOverrideEffect.execute = _vrai
    return retirer


def _instrumenter_A(tr: Trace):
    """Sonde de l'etage [A] : ce que `PerformAIAbility.execute` calcule PAR ACTEUR."""
    from engine.runner.abilities.behaviours.ai_control import PerformAIAbility
    _vrai = PerformAIAbility.execute

    def execute(self, entities, ectx):
        out = _vrai(self, entities, ectx)
        tr.note("A", allow_only_move=self.allow_only_move,
                a_override_movement=(self.override_movement is not None),
                a_custom_utility=(self.custom_utility is not None),
                a_utility_entity=(self.utility_entity is not None),
                a_get_ability_type=(self.get_ability_type is not None))
        return out
    PerformAIAbility.execute = execute

    def retirer():
        PerformAIAbility.execute = _vrai
    return retirer


def mesurer(state_name: str) -> dict:
    sid = P590._session()
    state_path = P590.LOGS / ("%s.json" % state_name)
    rid = P590.build(state_path, [
        "--seed", "777", "--board", P590.BOARD,
        "--p-units", "%s,%s" % (P590.CASTER_ID, P590.ALLY_ID),
        "--a-units", "%s,%s,%s" % (P590.TARGET_ID, P590.PREY_ID, P590.LONE_ID),
        "--place", "%s:%s" % (P590.CASTER_ID, P590.POS_CASTER),
        "--place", "%s:%s" % (P590.ALLY_ID, P590.POS_ALLY),
        "--a-place", "%s:%s" % (P590.TARGET_ID, P590.POS_TARGET),
        "--a-place", "%s:%s" % (P590.PREY_ID, P590.POS_PREY),
        "--a-place", "%s:%s" % (P590.LONE_ID, P590.POS_LONE)])
    try:
        from engine.runner.operations.summon_ai import _apply_active_ability
        from engine.runner.abilities.loki.summon import perform_ai_ability_unit_behaviour
        import engine.runner.abilities.loki.attempted_possession as AP
        from engine.runner.operations.change_unit_owner import (ChangeUnitOwnerOperation,
                                                                ResetUnitOwnerOperation)
        dec0 = P590.decision(sid, rid)
        ids = {n: P590.find(dec0, v) for n, v in (("caster", P590.CASTER_ID),
                                                  ("cible", P590.TARGET_ID),
                                                  ("proie", P590.PREY_ID),
                                                  ("seul", P590.LONE_ID),
                                                  ("allie", P590.ALLY_ID))}
        manquants = [n for n, u in ids.items() if u is None]
        if manquants:
            raise SystemExit("montage INCOMPLET : %s" % ",".join(manquants))
        ids = {n: int(u["id"]) for n, u in ids.items()}
        st0, _ = P590.load(sid, rid)
        dump = P590.rng_dump(sid, rid)
        P590.seed_offline_rng(st0, dump)

        # ---- COLONNE 1 : le corps HORS CAST, sous simulation du swap (le bras qui MARCHE) -----
        st_hors = copy.deepcopy(st0)
        P590.seed_offline_rng(st_hors, dump)
        tr_hors = Trace()
        pref = AP.attempted_possession_preferred_target(st_hors, ids["caster"], ids["cible"])
        ChangeUnitOwnerOperation.execute(st_hors, ids["cible"], ids["caster"])
        retirer = _instrumenter(tr_hors)
        try:
            import engine.runner.abilities.loki.summon as S
            hors = S.perform_ai_ability_unit_behaviour(
                st_hors, ids["cible"], False, 0,
                allowed_targets=(None if pref is None else {int(pref)}))
        finally:
            retirer()
        ResetUnitOwnerOperation.execute(st_hors, ids["cible"])

        # ---- COLONNE 2 : le FLUX DU CAST ------------------------------------------------------
        st_cast = copy.deepcopy(st0)
        P590.seed_offline_rng(st_cast, dump)
        tr_cast = Trace()
        retirer = _instrumenter(tr_cast)
        retirer_a = _instrumenter_A(tr_cast)
        retirer_g = _instrumenter_G(tr_cast, st_cast, ids["caster"])
        try:
            ret = _apply_active_ability(st_cast, ids["caster"], ids["cible"], P590.ABILITY)
        finally:
            retirer_g()
            retirer_a()
            retirer()

        # ---- ETAT VU PAR LE CAST au moment du `PerformAIAbility` ------------------------------
        # (re-joue le cast en s'ARRETANT a l'entree du corps, pour lire l'etat REEL)
        st_snap = copy.deepcopy(st0)
        P590.seed_offline_rng(st_snap, dump)
        snap = {}

        import engine.runner.abilities.loki.summon as S2
        _vrai = S2.perform_ai_ability_unit_behaviour

        def espion(state, unit_id, allow_move_action, move_amount, allowed_targets=None,
                   ability_type=None):
            if not snap:
                snap.update(_photo(state, int(unit_id), ids))
            return _vrai(state, unit_id, allow_move_action, move_amount,
                         allowed_targets=allowed_targets, ability_type=ability_type)
        S2.perform_ai_ability_unit_behaviour = espion
        try:
            _apply_active_ability(st_snap, ids["caster"], ids["cible"], P590.ABILITY)
        finally:
            S2.perform_ai_ability_unit_behaviour = _vrai

        # meme photo, mais dans le bras HORS CAST
        st_snap2 = copy.deepcopy(st0)
        P590.seed_offline_rng(st_snap2, dump)
        ChangeUnitOwnerOperation.execute(st_snap2, ids["cible"], ids["caster"])
        photo_hors = _photo(st_snap2, ids["cible"], ids)

        # ---- ENVELOPPE DE TIRAGE ---------------------------------------------------------------
        # Le cast qui aboutit laisse un ECART DE MONTANT avec le natif. Un ecart de montant sur UN
        # tirage ne dit RIEN tant qu'on n'a pas la dispersion : on rejoue donc le MEME cast avec N
        # graines de MT et on regarde si la valeur NATIVE tombe dans l'enveloppe du port. Ce n'est
        # pas un fit -- c'est la seule facon de savoir si l'ecart est un TIRAGE ou une FORMULE.
        enveloppe = []
        for graine in range(40):
            stg = copy.deepcopy(st0)
            from engine.runner.prng import IntBasedMersenneTwister
            stg.rng = IntBasedMersenneTwister(1000 + graine)
            r = _apply_active_ability(stg, ids["caster"], ids["cible"], P590.ABILITY)
            aiv = (((r or {}).get("diag") or {}).get("ai") or [{}])[0]
            acted = (aiv.get("acted") or [{}])[0]
            res = acted.get("result") or {}
            enveloppe.append(int(res.get("total") or 0))

        return {"ids": ids, "pref": pref, "hors": hors, "cast": ret,
                "trace_hors": tr_hors.lignes, "trace_cast": tr_cast.lignes,
                "photo_cast": snap, "photo_hors": photo_hors, "enveloppe": enveloppe,
                "dispose": lambda: P590.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)}
    except Exception:
        P590.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        raise


def _photo(state, uid: int, ids: dict) -> dict:
    """L'ETAT que le corps voit a son entree : owner, position, PV, effets, stat ATTACK, flags.

    C'est la seule chose qui differe entre les deux bras -- les ARGUMENTS, eux, sont traces par
    l'etage [B]. Un ecart d'etat qui ne serait pas photographie ici serait un angle mort."""
    from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                          StatsComponent, UnitComponent, UnitFlagsComponent)
    from engine.entities.stats import StatType
    out = {}
    for nom, eid in ids.items():
        e = state.get_entity(int(eid))
        if e is None:
            out[nom] = None
            continue
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        sc = e.get_component(StatsComponent)
        uc = e.get_component(UnitComponent)
        fl = e.get_component(UnitFlagsComponent)
        effs = []
        if state.effects is not None:
            effs = sorted(int(x.effect_type)
                          for x in (state.effects.by_unit.get(int(eid)) or []) if not x.consumed)
        try:
            atk = int(sc.ctx.stat(StatType.ATTACK)) if sc is not None else None
        except Exception:
            atk = None
        out[nom] = {"id": int(eid), "team": (oc.team if oc else None),
                    "player": (getattr(oc, "player", None) if oc else None),
                    "pos": ((pc.col, pc.row) if pc else None),
                    "hp": (hc.hp if hc else None), "alive": (uc.alive if uc else None),
                    "atk": atk, "effets": effs,
                    "flags": (getattr(fl, "flags", None) if fl is not None else None)}
    out["_acteur"] = int(uid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-name", default="probe_590r8_flux_du_cast")
    a = ap.parse_args()
    m = mesurer(a.state_name)
    try:
        print("=" * 92)
        print("[590-r8] flux du cast vs corps hors cast -- 1101 AttemptedPossession")
        print("=" * 92)
        print("ids : %s" % m["ids"])
        print("GetPreferredAttackTarget = %s" % m["pref"])
        print()
        print("--- COLONNE 1 : corps HORS CAST (le bras qui marche) ---")
        print("  retour : %s" % json.dumps(m["hors"], default=str)[:300])
        for l in m["trace_hors"]:
            print("    %s" % json.dumps(l, default=str)[:280])
        print()
        print("--- COLONNE 2 : FLUX DU CAST ---")
        print("  retour _apply_active_ability : %s" % json.dumps(m["cast"], default=str)[:600])
        for l in m["trace_cast"]:
            print("    %s" % json.dumps(l, default=str)[:280])
        print()
        env = sorted(x for x in (m.get("enveloppe") or []) if x)
        if env:
            print("--- ENVELOPPE DE TIRAGE du cast PORTE (40 graines de MT) ---")
            print("  min=%d  max=%d  moyenne=%d  n_non_nuls=%d/40"
                  % (env[0], env[-1], sum(env) // len(env), len(env)))
            print("  NATIF mesure par probe_590 : 7006 -- dans l'enveloppe : %s"
                  % (env[0] <= 7006 <= env[-1]))
        print()
        print("--- PHOTO DE L'ETAT a l'entree du corps ---")
        for nom in ("caster", "cible", "proie", "allie"):
            pc = (m["photo_cast"] or {}).get(nom)
            ph = (m["photo_hors"] or {}).get(nom)
            print("  %-7s cast=%s" % (nom, json.dumps(pc, default=str)))
            print("  %-7s hors=%s" % ("", json.dumps(ph, default=str)))
        print("=" * 92)
        return 0
    finally:
        m["dispose"]()


if __name__ == "__main__":
    sys.exit(main())
