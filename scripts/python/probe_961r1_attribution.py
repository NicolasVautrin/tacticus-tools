"""#961-r1 -- ATTRIBUTION de l'ecart `LivingLightning` a distance 1 (natif = 87,27 % du port).

Le residu #961 a mesure, A CIBLE IDENTIQUE et A TIRAGES MT IDENTIQUES (6/6), un degat live de
**87,27 %** du degat porte dans le regime `adjacent` (distance 1), alors que le regime `range2`
(distance 2) est BIT-EXACT. Deux hypotheses sont deja REFUTEES par l'auteur (melee/ranged force,
et l'elevation : le ratio est le meme sur deux configurations d'elevation distinctes).

CE PROBE NE FITTE AUCUN SCALAIRE. Il DECOMPOSE PAR ETAGE le cote PORT -- roll BRUT du coup, puis
`apply_pierce_and_modifiers` (percage + armure + modificateurs ATTAQUANT), puis `apply_all_modifiers`
(modificateurs DEFENSEUR) -- en instrumentant les foyers que `damage_ops/ability.py` resout dans SES
globals (patch pose sur `damage_ops.ability.<nom>`, la seule liaison qui morde ; cf. le PATCH-POINT
documente en tete de ce module). Rien n'est edite : ce sont des wrappers de MESURE.

La question a trancher EN PREMIER est celle du brief : l'ecart est-il dans le VECTEUR
`LivingLightning` ou dans le PIPELINE DE DEGAT PARTAGE ? La decomposition la tranche directement --
si un etage PORTE une valeur qu'il ne devrait pas porter, on voit LEQUEL, et on sait s'il est propre
au vecteur (ce que le vecteur PASSE au pipeline) ou interne au pipeline (ce que le pipeline FAIT
d'entrees identiques).

Usage (depuis scripts/python) :
    python probe_961r1_attribution.py --regimes adjacent,range2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_961_necron_passives as P                                      # noqa: E402
from engine.runner.operations.damage_ops import ability as ABIL            # noqa: E402
from engine.runner.operations import damage as DMG                        # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation as ADO   # noqa: E402

#: `applyAction` du pas, capture pour lire les EVENTS natifs (dont `On(0x3c = UnitBlocked)`).
LIVE_EVENTS = []


def _move_capturing(sid, rid, uid, col, row):
    r = P._r(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "move", "unitId": uid, "to": {"col": col, "row": row}}]}, 60)
    LIVE_EVENTS.append(r)
    return r


def _mods_repr(m) -> str:
    """Liste ASCII des champs NON VIDES d'un `DamageModifiers` (structure = celle du natif :
    listes de pourcentages + additifs plats)."""
    if m is None:
        return "None"
    out = []
    names = getattr(m, "__slots__", None) or list(getattr(m, "__dict__", {}) or {})
    for n in names:
        try:
            v = getattr(m, n)
        except AttributeError:
            continue
        if v is None:
            continue
        if isinstance(v, (list, tuple, set, dict)) and not v:
            continue
        if isinstance(v, (int, float)) and not v:
            continue
        out.append("%s=%r" % (n, v))
    return "{" + ", ".join(out) + "}" if out else "{}"


class Trace:
    """Capture par ETAGE, pour l'attaque du vecteur mesure. Une entree par COUP."""

    def __init__(self):
        self.armor = []
        self.att_mods = []
        self.def_mods = []
        self.hits_in = []
        self.hits_out = []
        self.elev = []
        self.trench = []
        self.pierce = []      # (roll_brut, profile_pierce, armor, sortie)
        self.after_def = []   # (entree, sortie)
        self.bounds = []      # (base_min, base_max) construits par `HitDamage`
        self.block = []       # sources de BLOCAGE vues par le port
        self.crit = []        # (chance, damage, enabled) rendus par `_crit_params`
        self.ice = []         # `ice_crit_damage_addition`
        self.crit_bonus = []  # (bonus, porteurs) de `GetCritDamageBonusFromEffects`

    def install(self):
        self._orig = {}
        for name in ("attacker_modifiers", "defender_modifiers", "defender_fixed_armor",
                     "apply_pierce_and_modifiers", "apply_all_modifiers",
                     "apply_elevation_bonus", "apply_trench_reduction",
                     "attack_hits_with_modifiers", "HitDamage"):
            self._orig[name] = getattr(ABIL, name)
        t = self

        o = self._orig

        def attacker_modifiers(*a, **k):
            mods, active = o["attacker_modifiers"](*a, **k)
            t.att_mods.append(_mods_repr(mods))
            return mods, active

        def defender_modifiers(*a, **k):
            mods, act = o["defender_modifiers"](*a, **k)
            t.def_mods.append(_mods_repr(mods))
            return mods, act

        def defender_fixed_armor(*a, **k):
            v = o["defender_fixed_armor"](*a, **k)
            t.armor.append(v)
            return v

        def apply_elevation_bonus(state, mods, att, tgt, *a, **k):
            before = _mods_repr(mods)
            r = o["apply_elevation_bonus"](state, mods, att, tgt, *a, **k)
            t.elev.append((before, _mods_repr(mods)))
            return r

        def apply_trench_reduction(state, mods, att, tgt, *a, **k):
            before = _mods_repr(mods)
            r = o["apply_trench_reduction"](state, mods, att, tgt, *a, **k)
            t.trench.append((before, _mods_repr(mods)))
            return r

        def attack_hits_with_modifiers(*a, **k):
            r = o["attack_hits_with_modifiers"](*a, **k)
            t.hits_in.append(k.get("weapon_hits", a[0] if a else None))
            t.hits_out.append(r)
            return r

        def apply_pierce_and_modifiers(value, profile_pierce, armor, mods, *a, **k):
            r = o["apply_pierce_and_modifiers"](value, profile_pierce, armor, mods, *a, **k)
            t.pierce.append((value, profile_pierce, armor, r, _mods_repr(mods)))
            return r

        def apply_all_modifiers(value, def_mods, *a, **k):
            r = o["apply_all_modifiers"](value, def_mods, *a, **k)
            t.after_def.append((value, r, _mods_repr(def_mods)))
            return r

        def HitDamage(base_min, base_max, *a, **k):
            """`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage` -- les BORNES du
            coup. C'est ce que le VECTEUR passe au PIPELINE : si elles sont justes et que le tirage
            en sort, l'ecart est dans le pipeline ; si elles sont fausses, il est dans le vecteur."""
            t.bounds.append((base_min, base_max))
            return o["HitDamage"](base_min, base_max, *a, **k)

        self._orig_cdb = DMG.crit_damage_bonus_from_effects

        def crit_damage_bonus_from_effects(carriers, att_ctx, *a, **k):
            """`IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects` -- le
            SECOND terme du `Math.Max(0, GetStat(10) + <ce bonus>)` de `CalculateCriticalDamage`.
            On trace aussi les PORTEURS pour savoir QUEL effet contribue."""
            r = self._orig_cdb(carriers, att_ctx, *a, **k)
            noms = []
            for (oid, effs) in (carriers or []):
                for e in (effs or []):
                    noms.append("%s:%s" % (oid, getattr(e, "name", None) or getattr(e, "effect_type", e)))
            t.crit_bonus.append((r, noms))
            return r

        DMG.crit_damage_bonus_from_effects = crit_damage_bonus_from_effects
        self._orig_ice = ABIL.ice_crit_damage_addition

        def ice_crit_damage_addition(*a, **k):
            r = self._orig_ice(*a, **k)
            t.ice.append(r)
            return r

        ABIL.ice_crit_damage_addition = ice_crit_damage_addition
        self._orig_crit = ADO._crit_params

        def _crit_params(*a, **k):
            """`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` etapes crit
            (`RollCritical` slot 0xa / `CalculateCriticalDamage` slot 0xb)."""
            r = self._orig_crit.__func__(*a, **k) if hasattr(self._orig_crit, "__func__") \
                else self._orig_crit(*a, **k)
            ctx = a[0] if a else k.get("ctx")
            from engine.entities.stats import StatType as _ST
            brut = None
            if ctx is not None:
                try:
                    brut = (ctx.stat(_ST.CRIT_CHANCE), ctx.stat(_ST.CRIT_DAMAGE))
                except Exception as exc:                            # pragma: no cover
                    brut = "ERR %s" % exc
            t.crit.append((k.get("hit_index"), r, brut))
            return r

        ADO._crit_params = staticmethod(_crit_params)
        self._orig_block = ADO._block_sources

        def _block_sources(*a, **k):
            """`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` -- les sources de
            BLOCAGE de la cible (chance, montant). C'est le seul canal SOUSTRACTIF PLAT du coup."""
            r = self._orig_block.__func__(*a, **k) if hasattr(self._orig_block, "__func__") \
                else self._orig_block(*a, **k)
            t.block.append(r)
            return r

        ADO._block_sources = staticmethod(_block_sources)
        ABIL.HitDamage = HitDamage
        ABIL.attacker_modifiers = attacker_modifiers
        ABIL.defender_modifiers = defender_modifiers
        ABIL.defender_fixed_armor = defender_fixed_armor
        ABIL.apply_elevation_bonus = apply_elevation_bonus
        ABIL.apply_trench_reduction = apply_trench_reduction
        ABIL.attack_hits_with_modifiers = attack_hits_with_modifiers
        ABIL.apply_pierce_and_modifiers = apply_pierce_and_modifiers
        ABIL.apply_all_modifiers = apply_all_modifiers

    def restore(self):
        for name, fn in self._orig.items():
            setattr(ABIL, name, fn)
        ADO._block_sources = self._orig_block
        ADO._crit_params = self._orig_crit
        ABIL.ice_crit_damage_addition = self._orig_ice
        DMG.crit_damage_bonus_from_effects = self._orig_cdb

    def dump(self, prefix=""):
        print("%s  bornes HitDmg  : %s" % (prefix, self.bounds))
        print("%s  block sources  : %s" % (prefix, self.block))
        print("%s  crit params    : %s" % (prefix, self.crit))
        print("%s  crit bonus eff : %s" % (prefix, self.crit_bonus))
        print("%s  ice crit add   : %s" % (prefix, self.ice))
        print("%s  armure         : %s" % (prefix, self.armor))
        print("%s  hits  in/out   : %s -> %s" % (prefix, self.hits_in, self.hits_out))
        for i, (b, a) in enumerate(self.elev):
            print("%s  elevation[%d]   : %s -> %s" % (prefix, i, b, a))
        for i, (b, a) in enumerate(self.trench):
            print("%s  trench[%d]      : %s -> %s" % (prefix, i, b, a))
        for i, m in enumerate(self.att_mods):
            print("%s  mods ATT[%d]    : %s" % (prefix, i, m))
        for i, m in enumerate(self.def_mods):
            print("%s  mods DEF[%d]    : %s" % (prefix, i, m))
        for i, (v, p, ar, r, m) in enumerate(self.pierce):
            print("%s  coup %d : roll=%s pierce=%s armure=%s -> %s   [modsATT %s]"
                  % (prefix, i, v, p, ar, r, m))
        for i, (v, r, m) in enumerate(self.after_def):
            print("%s  coup %d : apres DEF %s -> %s   [modsDEF %s]" % (prefix, i, v, r, m))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--board", default="C1_75")
    ap.add_argument("--regimes", default="adjacent,range2")
    ap.add_argument("--inactifs", action="store_true",
                    help="#961-r3 : capture `decisionView` avec `includeInactive: true`. Seede les "
                         "effets POSES mais INACTIFS a l'instant de la capture -- dont "
                         "`SupaCyborkBody_CritDmgReduction`, dont la condition geometrique "
                         "`HasAdjacentEnemies(Owner)` n'est vraie qu'APRES le pas mesure. "
                         "OPT-IN : il elargit l'etat charge, donc deux regimes qui ne le partagent "
                         "pas ne sont pas comparables.")
    ap.add_argument("--unit-stat", action="append", default=[],
                    help="patch per-unit du BC normalise, transmis a `rl_duel build`")
    ap.add_argument("--enemy-near", default=None,
                    help="remplace la CIBLE du montage : separe une grandeur du DEFENSEUR "
                         "d'une grandeur de l'ATTAQUANT ou d'une constante globale")
    args = ap.parse_args(argv)
    if args.enemy_near:
        P.LL_ENEMY_NEAR = args.enemy_near
        if args.enemy_near == P.LL_ENEMY_FAR:
            P.LL_ENEMY_FAR = "orksWarboss"          # le TEMOIN EXILE doit rester une AUTRE unite
        P.LL_A_UNITS = [P.LL_ENEMY_NEAR, P.LL_ENEMY_FAR]
        print("[961-r1] CONTROLE cible = %s (temoin exile %s)"
              % (args.enemy_near, P.LL_ENEMY_FAR))
    if args.unit_stat:
        # CONTROLE : on fait varier UNE entree d'etat (ex. `critChance=0`) pour voir si le DELTA
        # la suit. C'est de la decomposition par etage, pas un ajustement de scalaire.
        _b = P.build

        def build(seed, board, p_units, a_units, state_file, extra=(), **k):
            return _b(seed, board, p_units, a_units, state_file,
                      extra=tuple(extra) + tuple(args.unit_stat), **k)

        P.build = build
        print("[961-r1] CONTROLE --unit-stat : %s" % args.unit_stat)
    sid = P._resolve_session()
    if not sid:
        print("[961-r1] pas de session Frida")
        return 2
    ratios = {}
    bilan = []
    for seed in [s.strip() for s in args.seeds.split(",") if s.strip()]:
        for regime in args.regimes.split(","):
            regime = regime.strip()
            if not regime:
                continue
            print("=" * 96)
            print("[961-r1] SEED %s REGIME %s" % (seed, regime))
            t = Trace()
            t.install()
            del LIVE_EVENTS[:]
            _orig_move = P.move
            P.move = _move_capturing
            try:
                res = P.measure_ll(sid, seed, args.board, verbose=True, regime=regime,
                                   inactifs=args.inactifs)
            finally:
                P.move = _orig_move
                t.restore()
            did_crit, amount = None, None
            if LIVE_EVENTS:
                # Le DERNIER `applyAction` est le pas MESURE (les precedents sont les placements).
                ev = LIVE_EVENTS[-1]
                # Les EVENTS natifs vivent dans `actions[i].events` (`StreamEvent` :
                # kind/step/group/entity/tags). Les tags `Attack_DidCrit` / `Attack_DidBlock` /
                # `Amount` disent ce que le natif a REELLEMENT fait du coup.
                for act in (ev.get("actions") or []) if isinstance(ev, dict) else []:
                    for e in (act.get("events") or []):
                        tags = e.get("tags")
                        if isinstance(tags, str):
                            try:
                                import json as _j
                                tags = _j.loads(tags)
                            except Exception:
                                pass
                        if isinstance(tags, dict) and any(
                                k in tags for k in ("Amount", "Attack_DidCrit", "Attack_DidBlock")):
                            print("[961-r1]   EVENT %s/%s entity=%s tags=%s"
                                  % (e.get("kind"), e.get("step"), e.get("entity"), tags))
                            did_crit = tags.get("Attack_DidCrit")
                            amount = tags.get("Amount")
            if res is None:
                print("[961-r1] %s/%s : montage NON ABOUTI" % (seed, regime))
                continue
            live = {k: v for k, v in res["d_live"].items() if v}
            port = {k: v for k, v in res["d_port"].items() if v}
            print("[961-r1] DECOMPOSITION PORT (seed %s regime %s)" % (seed, regime))
            t.dump("   ")
            # STATS RESOLUES PAR LE NATIF (`combatSnapshot` = `GetStat`), cote a cote avec ce que
            # le port a lu : c'est ce qui separe << stat differente >> (seeding) de
            # << bonus applique a tort >> (canal d'effets).
            snap = (res.get("cap") or {}).get("snap") or {}
            # #961-r3 -- LE POINT DE BASCULE : l'effet `SupaCyborkBody_CritDmgReduction` (relique
            # 1475 EQUIPEE AU SEED sur `orksRuntherd`) est-il PUBLIE par le natif, et CONSTRUIT
            # cote port ? S'il est publie mais absent des porteurs, le defaut est au montage du
            # port ; s'il n'est meme pas publie, c'est un trou de CAPTATION (fenetre de reinject).
            tid = res["ids"].get(P.LL_ENEMY_NEAR)
            for u in ((res.get("cap") or {}).get("dec") or {}).get("units") or []:
                if int(u.get("id") or -1) != int(tid or -1):
                    continue
                noms = [(e.get("name"), e.get("effectType"), e.get("active"))
                        for e in (u.get("effects") or [])]
                print("[961-r1] effets PUBLIES par le natif sur la cible : %s" % noms)
                print("[961-r1]   SupaCyborkBody publie ? %s"
                      % any("SupaCybork" in str(n[0]) for n in noms))
            want_ids = {res["ids"].get(P.LL_CARRIER), res["ids"].get(P.LL_ENEMY_NEAR)}
            for u in (snap.get("units") or []):
                uid = u.get("id", u.get("unitId", u.get("entityId")))
                if uid is None or int(uid) not in want_ids:
                    continue
                # On CHERCHE la valeur 579 dans les stats resolues plutot que de la deviner : le
                # delta est CONSTANT, donc il vient d'une grandeur d'ETAT, pas du tirage.
                plat = {}
                for k, v in u.items():
                    if isinstance(v, (int, float)):
                        plat[k] = v
                    elif isinstance(v, dict):
                        for k2, v2 in v.items():
                            if isinstance(v2, (int, float)):
                                plat["%s.%s" % (k, k2)] = v2
                print("[961-r1] snapshot NATIF %s : %s"
                      % (res["vis_by_id"].get(int(uid), uid), plat))
                hits579 = {k: v for k, v in plat.items() if v in (579, -579, 1503, 2082)}
                if hits579:
                    print("[961-r1]   >>> grandeurs egales au DELTA (579) ou au crit natif : %s"
                          % hits579)
            print("[961-r1] live=%s port=%s tirages live=%s port=%s"
                  % (live, port, res["draws_live"], res["draws_port"]))
            if live and port and set(live) == set(port):
                k = next(iter(live))
                if port[k]:
                    ratios["%s/%s" % (seed, regime)] = float(live[k]) / float(port[k])
                    print("[961-r1] ratio live/port = %.6f  (cible %s)"
                          % (ratios["%s/%s" % (seed, regime)], res["vis_by_id"].get(k, k)))
                # LA LIGNE QUI TRANCHE : le DELTA ABSOLU, en regard du drapeau `Attack_DidCrit`
                # NATIF. Si le delta suit le CRIT et non la DISTANCE, l'ecart est attribue au canal
                # CRIT (pipeline partage), pas au vecteur.
                bilan.append((seed, regime, did_crit, amount, live[k], port[k],
                              abs(port[k]) - abs(live[k])))
    print("=" * 96)
    print("[961-r1] BILAN  seed / regime / DidCrit natif / Amount natif / live / port / delta")
    for row in bilan:
        print("[961-r1]   %-8s %-9s crit=%-5s amount=%-7s live=%-7s port=%-7s DELTA=%s" % row)
    crits = sorted({r[6] for r in bilan if r[2]})
    nocrits = sorted({r[6] for r in bilan if r[2] == 0})
    print("[961-r1] DELTAS sur coup CRITIQUE     : %s" % crits)
    print("[961-r1] DELTAS sur coup NON CRITIQUE : %s" % nocrits)
    if crits and nocrits:
        print("[961-r1] VERDICT : le delta suit le CRIT (%s) et non la DISTANCE ; "
              "hors crit le delta est %s" % (crits, nocrits))
    else:
        print("[961-r1] NON CONCLUANT : il manque un temoin (crit=%s, non-crit=%s) -- rejouer "
              "d'autres seeds jusqu'a obtenir les DEUX regimes de crit sur CHAQUE distance."
              % (len(crits), len(nocrits)))
    print("[961-r1] RATIOS : %s" % {k: round(v, 6) for k, v in ratios.items()})
    # NON-DEGENERESCENCE : un ratio ne vaut que si les deux cotes sont NON NULS (deja garanti par
    # `port[k]` et l'appartenance a `live`), et l'invariance du ratio ne se conclut QUE sur
    # plusieurs TIRAGES INDEPENDANTS -- deux configurations d'elevation d'une MEME capture ne sont
    # pas independantes (l'une est l'autre x1.5).
    if len(ratios) > 1:
        vals = sorted(ratios.values())
        print("[961-r1] amplitude des ratios : min=%.6f max=%.6f ecart=%.6f"
              % (vals[0], vals[-1], vals[-1] - vals[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
