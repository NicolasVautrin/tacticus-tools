"""#953-r2 -- DECOMPOSITION de l'ecart PORT > NATIF sur une attaque RANGED d'`emperNoiseMarine`.

CE QUE CE PROBE MESURE
----------------------
Le bras `oa_away` de `probe_953_954` (TEMOIN : Adamatar adjacent a l'ATTAQUANT, pas a la victime)
rendait, avec `emperNoiseMarine` << Shiron >> en attaquant RANGED, natif 4699 contre port 6396
(+36 %), et le MEME ecart avec le port neutralise (`--mutate`) : l'ecart est ETRANGER au lot
#953/#954. Le bras `oa_melee`, MEME attaquant MEME cible, rend `1996 == 1996`.

Ce probe rejoue exactement ce bras et, sur le MEME `State` et le MEME flux RNG, NEUTRALISE un
CANAL a la fois cote port (`--isoler`), pour repondre a << lequel des bonus le port applique-t-il
que le natif n'applique pas ? >>. Chaque canal est une CLASSE d'effet (sa
`create_effect_damage_bonus_for_attack` rend `None`) ou un TRIGGER (retire du registre).

Le discriminant n'est PAS un scalaire fitte : un canal ne << explique >> l'ecart que si le rejeu
neutralise rend le ledger natif COUP PAR COUP, a l'unite.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import hexgeo                                                     # noqa: E402
import probe_953_954_skullsmasher_obsessive_annunciation as P     # noqa: E402
from probe_r6_round_materialize import _mkrpc                     # noqa: E402

BOARD = "MC1_67"
SEED = "777"

ADA = P.ADA                       # `emperKakophonist` << Adamatar >>
ATT = "emperNoiseMarine"          # << Shiron >> -- l'attaquant RANGED du residu
VICTIM = P.VICTIM                 # `orksNob`
SACRIFICE = P.SACRIFICE           # figurant LOIN (cf. `probe_953_954.run_oa`)


# --------------------------------------------------------------------------- neutralisations


class _IsoleEffets:
    """Neutralise le canal DEGAT-ATTAQUANT de N classes d'effet, par leur nom d'`EffectType`.

    On ne remplace PAS la classe par `BaseEffect` (ca neutraliserait aussi ses autres canaux :
    defense, armure, crit) : on ne coupe que `create_effect_damage_bonus_for_attack`, le slot
    natif `CreateEffectDamageBonusForAttack` / `CreateDamageModifier`."""

    def __init__(self, noms):
        self.noms = list(noms or [])
        self._old = {}

    def __enter__(self):
        from engine.entities.effects.factory import EFFECT_CLASSES
        for n in self.noms:
            cls = EFFECT_CLASSES.get(n)
            if cls is None:
                continue
            self._old[n] = (cls, cls.__dict__.get("create_effect_damage_bonus_for_attack"))
            cls.create_effect_damage_bonus_for_attack = (
                lambda self, *a, **k: None)                     # type: ignore[assignment]
        return self

    def __exit__(self, *exc):
        for n, (cls, old) in self._old.items():
            if old is None:
                cls.__dict__.pop("create_effect_damage_bonus_for_attack", None)
                try:
                    delattr(cls, "create_effect_damage_bonus_for_attack")
                except AttributeError:
                    pass
            else:
                cls.create_effect_damage_bonus_for_attack = old
        return False


class _IsoleTriggers:
    """Retire N entrees d'`ABILITY_TRIGGERS` (par nom d'ability)."""

    def __init__(self, noms):
        self.noms = list(noms or [])
        self._old = {}

    def __enter__(self):
        from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
        for n in self.noms:
            if n in ABILITY_TRIGGERS:
                self._old[n] = ABILITY_TRIGGERS.pop(n)
        return self

    def __exit__(self, *exc):
        from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
        ABILITY_TRIGGERS.update(self._old)
        return False


#: Les canaux isolables, par nom court. Chaque entree = (effets neutralises, triggers retires).
CANAUX = {
    "heavyweapon":  (["HeavyWeapon_ExtraDmg"], []),
    "crescendo":    (["TerrifyingCrescendo_ExtraDmg"], []),
    "crescendo-trg": ([], ["TerrifyingCrescendo"]),
    "thrill":       ([], ["ThrillSeekers"]),
    "suppressive":  ([], ["SuppressiveFire"]),
    "oa":           (["ObsessiveAnnunciation_ExtraDmg", "ObsessiveAnnunciation_ExtraCritDmg"], []),
}


def _replay(cap, board, att_id, tgt_id, effets=(), triggers=(), trace=False,
            place_remontee=False):
    """Rejoue l'attaque OFFLINE sur le `State` capte et le flux RNG capte, canaux neutralises.

    `trace` : loggue, pour CHAQUE effet actif de l'attaquant, l'`EffectBonus` qu'il verse (le slot
    `CreateEffectDamageBonusForAttack`). L'instrumentation ENCADRE la boucle native portee
    (`engine.entities.effects._attacker_effect_bonuses`, resolue globalement dans son module donc
    le patch MORD) et rejoue la meme boucle a des fins d'affichage -- ces constructeurs sont purs
    (ils allouent un `EffectBonus`), et le total rendu est CELUI DE L'ORIGINAL."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    journal = []
    with _IsoleEffets(effets), _IsoleTriggers(triggers):
        import engine.entities.effects as E
        orig = E._attacker_effect_bonuses

        def _wrap(effects, is_ranged=None, is_normal_attack=True, has_moved=None,
                  target_traits=None, is_prediction=False, target_armor_reduced=None,
                  att_ctx=None):
            out = orig(effects, is_ranged, is_normal_attack, has_moved, target_traits,
                       is_prediction, target_armor_reduced, att_ctx)
            if trace:
                for e in E._as_effects(effects):
                    db = e.create_effect_damage_bonus_for_attack(
                        is_ranged, has_moved, target_traits=target_traits,
                        is_prediction=is_prediction, is_normal_attack=is_normal_attack,
                        target_armor_reduced=target_armor_reduced, att_ctx=att_ctx)
                    journal.append({"cls": type(e).__name__,
                                    "type": getattr(e, "effect_type", None),
                                    "level": getattr(e, "level", None),
                                    "bonus": None if db is None else _fmt_bonus(db)})
            return out

        if trace:
            E._attacker_effect_bonuses = _wrap
        try:
            st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
            rng = IntBasedMersenneTwister()
            rng.mt = list(cap["rng"]["mt"])
            rng.mti = cap["rng"]["mti"]
            st.rng = rng
            hc = st.get_entity(int(tgt_id)).get_component(HealthComponent)
            hp0 = int(hc.hp)
            lvl0 = _effect_level(st, att_id, "TerrifyingCrescendo_ExtraDmg")
            runner = Runner(st).install_default_handlers(20)
            if place_remontee:
                # CONTRE-EPREUVE : rejoue `On(PreAttack = 5)` AVANT l'attaque, ce qui reconstitue
                # EXACTEMENT la place d'ou #953-r2 l'a fait redescendre (au-dessus d'
                # `attacker_modifiers`) : la cascade `SuppressiveFire` -> `Pinned` ->
                # `On(PreEffectAdded)` -> `TerrifyingCrescendo` monte d'un cran de plus, et les
                # coups voient donc niveau+1 comme avant le correctif. Aucun tirage `state.rng`
                # n'est consomme par ce vecteur chez un porteur sans `LetTheGalaxyBurn`, donc le
                # ledger mute doit valoir l'ANCIEN port a l'unite -- c'est ce que le test assert.
                from engine.runner.operations.triggers.dispatch.attack import pre_attack_triggers
                pre_attack_triggers(st, int(att_id), int(tgt_id), ranged=True)
            runner.apply(AttackUnitMessage(int(att_id), int(tgt_id)))
            last = runner.damage_handler.last or {}
            lvl1 = _effect_level(st, att_id, "TerrifyingCrescendo_ExtraDmg")
            return {"hp_delta": hp0 - int(hc.hp), "total": last.get("total"),
                    "per_hit": list(last.get("per_hit") or []),
                    "crescendo_level_before": lvl0, "crescendo_level_after": lvl1,
                    "journal": journal}
        finally:
            if trace:
                E._attacker_effect_bonuses = orig


def _fmt_bonus(db):
    """Toutes les faces de l'`EffectBonus`, y compris NULLES : un champ tu se lirait comme un
    canal absent (et c'est exactement ce qu'un filtre << non vide >> a d'abord fait ici)."""
    d = {}
    for k in ("additive", "pct_list", "percent_increase", "percent_decrease", "flat",
              "armor_penetration", "native_face"):
        if hasattr(db, k):
            d[k] = getattr(db, k)
    if not d:
        d = {k: v for k, v in vars(db).items()} if hasattr(db, "__dict__") else {"repr": repr(db)}
    return d


def _effect_level(st, uid, name):
    """Niveau de l'effet nomme porte par `uid` (None s'il n'est pas la)."""
    eff = getattr(st, "effects", None)
    if eff is None:
        return None
    from engine.entities.effect_type import EffectType
    want = int(getattr(EffectType, name))
    for e in (eff.by_unit.get(int(uid)) or []):
        if getattr(e, "effect_type", None) is not None and int(e.effect_type) == want:
            return getattr(e, "level", None)
    return None


def _native_effects(dv, uid):
    """`(effect_type, level)` des effets natifs portes par `uid`."""
    u = P._unit(dv, uid) or {}
    out = []
    for e in (u.get("effects") or []):
        out.append((e.get("effectType"), e.get("level"), e.get("name")))
    return out


# --------------------------------------------------------------------------- bras


def run(isoler=(), trace=False, seed=SEED, board=BOARD, melee=False, repeats=1,
        place_remontee=False, verbose=True) -> dict:
    g = P.geometry(board)
    att_tile = g["M"] if melee else g["R"]
    ada_tile = g["A2"]                                   # TEMOIN : adjacent a l'ATTAQUANT
    p_units, a_units = [ADA, ATT], [VICTIM, SACRIFICE]
    places_p = [(ADA, ada_tile), (ATT, att_tile)]
    places_a = [(VICTIM, g["V"]), (SACRIFICE, g["SACFAR"])]
    extra = ["--hp-target", "400000", "--hp-player", "400000"]
    rid, err = P._build(p_units, a_units, places_p, places_a, seed=seed, board=board,
                        crit="0,0", extra=extra)
    if rid is None:
        return {"error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        geo = P._geo_assert(rpc, rid, {ADA: ada_tile, ATT: att_tile, VICTIM: g["V"]})
        from engine.entities.pathfinding.board import Board
        bobj = Board(geo["bg"]["tiles"], adjacency="native_sym")
        dv = P._view(rpc, rid, inactive=True)
        ids = {v: int(P._by_vis(dv, v)["id"]) for v in (ADA, ATT, VICTIM, SACRIFICE)
               if P._by_vis(dv, v) is not None}
        out = {"isoler": list(isoler), "melee": bool(melee), "repeats": int(repeats),
               "runner": rid, "ids": ids,
               "geo": {"pos": geo["pos"], "elev": geo["elev"], "fail": geo["fail"]}}
        if geo["fail"]:
            return _done(out, verbose)
        att_id, tgt_id = ids[ATT], ids[VICTIM]
        out["geo"]["d_ada_victim"] = hexgeo.distance(geo["pos"][ADA], geo["pos"][VICTIM])
        out["geo"]["d_ada_att"] = hexgeo.distance(geo["pos"][ADA], geo["pos"][ATT])
        out["geo"]["d_att_victim"] = hexgeo.distance(geo["pos"][ATT], geo["pos"][VICTIM])
        na = P._normal_attack_id(dv, att_id)
        if na is None:
            out["error"] = "id d'attaque normale introuvable pour %s" % ATT
            return _done(out, verbose)
        effets, triggers = [], []
        for c in isoler:
            e, t = CANAUX[c]
            effets += e
            triggers += t
        #: N attaques SUCCESSIVES du meme attaquant sur la meme cible. Le discriminant du residu est
        #: le NIVEAU du crescendo VU PAR LES COUPS : la passe 1 le trouve absent, les suivantes le
        #: trouvent deja pose. Un port qui monte le stack TROP TOT diverge des la passe 1 ; un port
        #: qui le monte au bon etage doit rester egal a TOUTES les passes.
        passes = []
        for k in range(int(repeats)):
            if k:
                P._ensure_can_act(rpc, rid, att_id)
            dvk = P._view(rpc, rid, inactive=True)
            before = _native_effects(dvk, att_id)
            cap = P._capture(rpc, rid)
            _res, hits = P._attack(rpc, rid, att_id, tgt_id, na)
            dv2 = P._view(rpc, rid, inactive=True)
            port = _replay(cap, bobj, att_id, tgt_id, effets=effets, triggers=triggers,
                           trace=trace)
            mut = (_replay(cap, bobj, att_id, tgt_id, effets=effets, triggers=triggers,
                           place_remontee=True) if place_remontee else None)
            passes.append({
                "mutant": None if mut is None else {"per_hit": mut["per_hit"],
                                                    "total": mut["total"]},
                "passe": k,
                "att_effects_before": before,
                "att_effects_after": _native_effects(dv2, att_id),
                "tgt_effects_after_native": P._effect_types(dv2, tgt_id),
                "native": {"hits": hits, "n": len(hits), "total": sum(hits)},
                "port": {"per_hit": port["per_hit"], "n": len(port["per_hit"]),
                         "total": port["total"],
                         "crescendo_level_before": port["crescendo_level_before"],
                         "crescendo_level_after": port["crescendo_level_after"]},
                "journal": port["journal"]})
        out["passes"] = passes
        if passes:
            out.update({k: passes[0][k] for k in ("att_effects_before", "att_effects_after",
                                                  "tgt_effects_after_native", "native", "port",
                                                  "journal")})
        return _done(out, verbose)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _done(out, verbose):
    if verbose:
        _report(out)
    return out


def _report(r):
    print("[953-r2] isoler=%-28s melee=%-5s runner=%s"
          % (",".join(r.get("isoler") or []) or "-", r.get("melee"), r.get("runner")))
    if r.get("error"):
        print("       ERREUR : %s" % r["error"])
        return
    g = r.get("geo") or {}
    print("       geo pos=%s elev=%s" % (g.get("pos"), g.get("elev")))
    print("       d(ada,victim)=%s d(ada,att)=%s d(att,victim)=%s"
          % (g.get("d_ada_victim"), g.get("d_ada_att"), g.get("d_att_victim")))
    for f in (g.get("fail") or []):
        print("       %s" % f)
    for pas in (r.get("passes") or []):
        print("       --- passe %d ---" % pas["passe"])
        print("       attaquant AVANT (natif) : %s" % (pas["att_effects_before"],))
        print("       attaquant APRES (natif) : %s" % (pas["att_effects_after"],))
        print("       cible   APRES (natif)   : %s" % (pas["tgt_effects_after_native"],))
        n, p = pas["native"], pas["port"]
        print("       NATIF  n=%-2s total=%-9s hits=%s"
              % (n.get("n"), n.get("total"), n.get("hits")))
        print("       PORT   n=%-2s total=%-9s hits=%s"
              % (p.get("n"), p.get("total"), p.get("per_hit")))
        print("       PORT   crescendo level %s -> %s"
              % (p.get("crescendo_level_before"), p.get("crescendo_level_after")))
        if n.get("total") is not None and p.get("total") is not None:
            d = int(p["total"]) - int(n["total"])
            print("       ECART  port - natif = %+d (%.1f %%)"
                  % (d, 100.0 * d / max(1, int(n["total"]))))
        if pas.get("mutant"):
            m = pas["mutant"]
            print("       MUTANT (place REMONTEE) total=%-9s hits=%s"
                  % (m.get("total"), m.get("per_hit")))
        for j in (pas.get("journal") or []):
            print("       [bonus] %-42s type=%-6s level=%-4s %s"
                  % (j["cls"], j["type"], j["level"], j["bonus"]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--isoler", default="", help="canaux a neutraliser (%s)" % ",".join(CANAUX))
    ap.add_argument("--trace", action="store_true", help="journal des EffectBonus par effet")
    ap.add_argument("--melee", action="store_true", help="bras MELEE (temoin a ecart nul)")
    ap.add_argument("--repeats", type=int, default=1, help="nb d'attaques SUCCESSIVES mesurees")
    ap.add_argument("--place-remontee", action="store_true",
                    help="joue AUSSI le rejeu MUTANT (place d'avant #953-r2)")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    iso = [x for x in a.isoler.split(",") if x]
    for c in iso:
        if c not in CANAUX:
            raise SystemExit("[953-r2] canal inconnu : %s (connus : %s)" % (c, ",".join(CANAUX)))
    r = run(isoler=iso, trace=a.trace, seed=a.seed, board=a.board, melee=a.melee,
            repeats=a.repeats, place_remontee=a.place_remontee, verbose=not a.json)
    if a.json:
        print(json.dumps(r, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
