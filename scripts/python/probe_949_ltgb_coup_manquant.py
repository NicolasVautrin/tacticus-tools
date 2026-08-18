"""#949 -- `LetTheGalaxyBurn` (1477) : LE COUP QUE LE NATIF AJOUTE ET QUE LE PORT NE MATERIALISE PAS.

Le residu est ne d'une observation HORS PERIMETRE de #947 (`docs/rl/case-947-948-passifs-extra-damage.md`
Sec.6) : avec ses traits NATIFS, `blackHaarken` rendait un ledger natif de **8 coups**
`[1779, 1539, 1713, 1688, 1520, 1885, 1704, 66723]` la ou le rejeu offline depuis la MEME capture en
rendait **6** pour 10 124 pts.

CE PROBE NE FITTE AUCUN SCALAIRE. Il DECOMPOSE, dans cet ordre :

  1. **ATTRIBUTION** -- chaque event de degat est ventile par son `Effect_Type` (tag natif), donc
     « coup d'attaque » (`None`/`0`/`1009`) et « autre canal » (DoT de tuile, effet...) ne sont
     JAMAIS additionnes dans le meme compte. C'est le premier etage, et il suffit a dire si l'ecart
     porte sur un COUP ou sur un canal etranger a l'attaque.
  2. **COMPTE DE COUPS** -- combien de coups d'attaque de chaque cote (natif vs port).
  3. **MAGNITUDE** -- la valeur de chaque coup, et celle du coup surnumeraire.
  4. **GATE** -- lequel des deux disjoints de
     `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`
     (`TargetHasTileEffect | IsPersistentData`) tenait cote NATIF, lu dans l'etat live (les
     status-effects de la tuile de la cible), et lequel tient cote PORT.

Bras :
  * `--bras reproduction` : le montage de #947 (trois attaques enchainees, deux kills de HERO puis
    l'attaque de mesure) **SANS** `--unit-stat "blackHaarken:Traits=[]"` -- c'est-a-dire le regime
    EXACT dans lequel l'ecart a ete observe.
  * `--bras isolation` : Haarken (traits natifs) contre UNE seule cible a gros PV, N attaques
    successives. Aucun `HeadClaimer` en jeu (aucun kill) -> le seul canal de coup surnumeraire est
    `LetTheGalaxyBurn`. Mesure le taux d'apparition natif ET port sur le MEME flux RNG.

    python probe_949_ltgb_coup_manquant.py --bras reproduction --verbose
    python probe_949_ltgb_coup_manquant.py --bras isolation --attaques 6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                          # noqa: E402
import probe_947_948_extra_damage_passives as P947                     # noqa: E402

BOARD = "MC1_67"
SEED = "4321"

HAARKEN = P947.HAARKEN                  # blackHaarken -- traits natifs : Hero/LetTheGalaxyBurn/Flying/Terrifying
VICTIME_HERO_1 = P947.VICTIME_HERO_1
VICTIME_HERO_2 = P947.VICTIME_HERO_2
CIBLE_FINALE = P947.CIBLE_FINALE

#: `Effect_Type` des events de degat qui SONT des coups de l'attaque en cours. `1009` = overwatch,
#: deja retenu comme coup d'attaque par les probes en place (cf. `probe_366_r1_psychic_stalk.py`).
EFFECT_TYPES_COUP = (None, 0, 1009)


def _events(res, tid):
    """TOUS les events de degat portes sur `tid`, avec leurs tags COMPLETS -- pas seulement leur
    `Amount`. C'est la difference avec `probe_947._attack`, qui agrege en aveugle : un event qui
    n'est pas un coup d'attaque (DoT de tuile...) y devient indiscernable d'un coup."""
    out = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" not in td:
                continue
            if int(td.get("Target_Id", td.get("TargetId", tid)) or tid) != int(tid):
                continue
            out.append({"amount": int(td["Amount"]),
                        "effect_type": td.get("Effect_Type"),
                        "source_id": td.get("Source_Id"),
                        "name": ev.get("name") or ev.get("type") or ev.get("eventType"),
                        "tags": td})
    return out


def _ventiler(evs):
    """Etage 1 -- ATTRIBUTION. Rend `(coups, autres)` : les coups d'attaque d'un cote, tout le reste
    ventile par `Effect_Type` de l'autre."""
    coups = [e for e in evs if e["effect_type"] in EFFECT_TYPES_COUP]
    autres = [e for e in evs if e["effect_type"] not in EFFECT_TYPES_COUP]
    return coups, autres


def _tile_status_live(rpc, rid, pos):
    """Les status-effects DYNAMIQUES de la tuile `pos` cote NATIF -- l'entree du disjoint
    `TargetHasTileEffect` (`IdunBattleLogic.Entities.DSLTriggers$$HasTileStatusEffect`). Lu par le RPC
    `tileMeta` si le host l'expose, sinon `None` (PAS mesure -- jamais rendu comme un vide)."""
    try:
        tm = rpc("tileMeta", {"runnerId": rid}, 60)
    except Exception:
        return None
    for t in (tm.get("tiles") or tm.get("meta") or []):
        p = t.get("pos") or t
        try:
            if int(p.get("col")) == int(pos[0]) and int(p.get("row")) == int(pos[1]):
                return [e.get("name") or e.get("effectType") for e in (t.get("effects") or [])]
        except Exception:
            continue
    return []


def _port_gate(cap, board, att_id, tgt_id):
    """Etage 4 cote PORT -- ce que le gate de `LetTheGalaxyBurnEffect` VOIT dans l'etat charge, AVANT
    toute attaque : le flag persistant sur l'attaquant, et les status-effects de la tuile de la cible.
    Aucune attaque n'est jouee ici : on lit l'ENTREE du gate, pas son effet."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import PositionComponent, PersistentDataComponent
    from engine.runner.damage_model import tile_status_effects_by_pos
    from engine.entities.effects.loki.hits import LET_THE_GALAXY_BURN_PERSISTENT_KEY

    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
    e = st.get_entity(int(tgt_id))
    pc = e.get_component(PositionComponent) if e is not None else None
    tfx = None
    if pc is not None:
        tfx = list((tile_status_effects_by_pos(st, [(pc.col, pc.row)]) or {}).get((pc.col, pc.row))
                   or ())
    a = st.get_entity(int(att_id))
    pdc = a.get_component(PersistentDataComponent) if a is not None else None
    armed = bool(pdc is not None and LET_THE_GALAXY_BURN_PERSISTENT_KEY in (pdc.data or {}))
    effets = []
    if st.effects is not None:
        effets = [(x.name, x.effect_type) for x in st.effects.by_unit.get(int(att_id), [])
                  if not x.consumed]
    return {"tuile_cible": tfx, "flag_arme": armed, "effets_attaquant": effets}


def _replay_trace(cap, board, paires):
    """LA DECOMPOSITION PAR ETAGE, cote PORT. Rejoue l'attaque en instrumentant les QUATRE etages
    que le coup `LetTheGalaxyBurn` doit traverser, du plus haut au plus bas :

      1. `LetTheGalaxyBurnArmAbility.matches`      -- le trigger de POSE est-il seulement CONSULTE,
                                                      et que rend-il ? (`On(PreAttack)` emis ?)
      2. `MaybeTrigger.should_trigger`             -- le tirage `Maybe(ConfigConst 0x2a)` du natif ;
      3. `LetTheGalaxyBurnEffect.additional_hit_groups` -- le gate du COUP : ce qu'il LIT (flag
                                                      persistant, status-effects de la tuile,
                                                      `attack_hit_damage`) et ce qu'il REND ;
      4. le ledger final.

    Un etage muet est un resultat : si (1) n'est jamais appele, l'ecart est un probleme d'EMISSION ;
    si (3) est appele avec `armed = False`, c'est le tirage ; si (3) rend un groupe et que le ledger
    ne le porte pas, c'est le CANAL."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.triggers.loki import let_the_galaxy_burn as LTGB
    from engine.entities.effects.loki import hits as HITS
    from engine.entities import triggers as TRG
    from engine.entities.effects.loki.hits import LET_THE_GALAXY_BURN_PERSISTENT_KEY

    trace = {"arm_matches": [], "maybe": [], "gate": [], "ledger": None}
    o_match = LTGB.LetTheGalaxyBurnArmAbility.matches
    o_exec = LTGB.LetTheGalaxyBurnArmAbility.execute_behaviour
    o_maybe = TRG.MaybeTrigger.should_trigger
    o_gate = HITS.LetTheGalaxyBurnEffect.additional_hit_groups

    def _m(self, state, ev):
        r = o_match(self, state, ev)
        trace["arm_matches"].append({"owner": int(self.owner_id), "actor": ev.actor_id,
                                     "target": ev.target_id, "retour": bool(r)})
        return r

    def _mb(self, ents):
        r = o_maybe(self, ents)
        trace["maybe"].append(bool(r))
        return r

    def _g(self, ctx=None):
        c = ctx or {}
        tfx, tp = c.get("tile_effects_by_pos"), c.get("t_pos")
        r = o_gate(self, ctx)
        trace["gate"].append({
            "appele": True,
            "flag_arme": LET_THE_GALAXY_BURN_PERSISTENT_KEY in (c.get("persistent_data") or ()),
            "tuile_cible": (None if (tfx is None or tp is None)
                            else sorted((tfx or {}).get(tuple(tp)) or ())),
            "attack_hit_damage": c.get("attack_hit_damage"),
            "retour": r})
        return r

    # ETAGE 3bis -- le CANAL : ce que `execute_additional_hits` recoit et ce qu'il rend. Sans lui, un
    # groupe rendu par le gate et perdu ensuite est indiscernable d'un gate muet.
    from engine.runner.operations.damage_ops import normal as NRM
    o_exec_ah = NRM.execute_additional_hits

    # SIGNATURE COMPLETE, et pas un `*a, **k` apres les six premiers (#962) : le cliquet
    # `test_additional_hits_variant_signatures_offline` retient toute fonction dont les parametres
    # COMMENCENT par ceux du port, puis exige qu'elle les porte TOUS -- un hybride fige l'ordre des
    # six premiers tout en masquant les quatorze suivants, donc un parametre ajoute au port ne
    # leverait ici qu'a la prochaine passe LIVE de ce harnais. Defauts recopies du port
    # (`engine/runner/operations/additional_hits.py::execute_additional_hits`).
    def _eah(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor, hit_mult,
             block_sources, shc, spread_pct=None, extra_pierce=0, bonus_hit_chance=None,
             hit_index0=0, crit_allowed0=True, attack_profile=None, hit_interceptor=None,
             failed_block0=None, damaging_done0=False, source_ability=None,
             attacker_mods_for_profile=None):
        # #963-r2 : `damaging_done0` (`isFirstDamagingHit`) est TRANSMIS tel quel -- cette
        # substitution est un OBSERVATEUR, elle ne fait varier aucun etage.
        r = o_exec_ah(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor,
                      hit_mult, block_sources, shc, spread_pct, extra_pierce, bonus_hit_chance,
                      hit_index0, crit_allowed0, attack_profile, hit_interceptor, failed_block0,
                      # #1020-r6 : `source_ability` est TRANSMIS tel quel -- l'avaler desarmerait
                      # le canal `AbilityEntities+0x98` dans le rejeu de ce probe, et pas dans le
                      # port livre : l'ecart se lirait comme une regression du port.
                      # #488-r3 : le re-collecteur de mods au profil DU GROUPE est TRANSMIS tel
                      # quel, meme raison que `source_ability` ci-dessus.
                      damaging_done0, source_ability, attacker_mods_for_profile)
        trace.setdefault("canal", []).append(
            {"groupes_recus": list(groups or []),
             "retour": (None if r is None else {"groups": r.get("groups"), "hits": r.get("hits"),
                                                "total": r.get("total"),
                                                "per_hit": r.get("per_hit"),
                                                "profiles": r.get("profiles")})})
        return r

    NRM.execute_additional_hits = _eah
    LTGB.LetTheGalaxyBurnArmAbility.matches = _m
    TRG.MaybeTrigger.should_trigger = _mb
    HITS.LetTheGalaxyBurnEffect.additional_hit_groups = _g
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        from engine.runner.components import HealthComponent
        h0 = None
        for att, tgt in paires:
            e = st.get_entity(int(tgt))
            hc = e.get_component(HealthComponent) if e is not None else None
            if h0 is None and hc is not None:
                h0 = int(hc.hp)
            runner.apply(AttackUnitMessage(int(att), int(tgt)))
        last = runner.damage_handler.last or {}
        ah = last.get("additional_hits") or {}
        # LE LEDGER COMPLET n'est PAS `last["per_hit"]` : ce champ ne porte que la PHASE D'ARME.
        # Les coups du canal #179 vivent dans `last["additional_hits"]`, canal SEPARE par conception
        # (`damage_ops/normal.py` rend les deux cote a cote). `hp_delta` est l'arbitre : c'est le
        # retrait REEL de PV, insensible a la facon dont le port ventile ses canaux.
        trace["ledger"] = {
            "arme_total": last.get("total"), "arme_per_hit": last.get("per_hit"),
            "additionnels_total": ah.get("total"), "additionnels_per_hit": ah.get("per_hit"),
            "complet_per_hit": list(last.get("per_hit") or []) + list(ah.get("per_hit") or []),
            "complet_total": int(last.get("total") or 0) + int(ah.get("total") or 0),
            "hp_delta": (None if (h0 is None or hc is None) else h0 - int(hc.hp))}
    finally:
        LTGB.LetTheGalaxyBurnArmAbility.matches = o_match
        LTGB.LetTheGalaxyBurnArmAbility.execute_behaviour = o_exec
        TRG.MaybeTrigger.should_trigger = o_maybe
        HITS.LetTheGalaxyBurnEffect.additional_hit_groups = o_gate
        NRM.execute_additional_hits = o_exec_ah
    return trace


def _dump(cap, path):
    """Persiste une capture live pour rejouer OFFLINE, sans reconstruire un runner (le budget est
    partage). `board` n'y est pas : il se re-derive du `boardGraph` du meme board id."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(cap), encoding="utf-8")


# --------------------------------------------------------------------------- bras REPRODUCTION


def _bras_reproduction(rpc, board_id, seed, verbose, dump=None):
    """Le montage de #947, mot pour mot, MOINS le `--unit-stat "blackHaarken:Traits=[]"` qui isolait
    la mesure. Les traits natifs de Haarken sont donc en jeu, dont `LetTheGalaxyBurn`."""
    board, err = P947._sonde_graphe(rpc, board_id, seed)
    if board is None:
        return {"verdict": "indisponible", "cause": err}
    centre, ring = P947._tuile_a_six_voisins(board)
    if centre is None:
        return {"verdict": "indisponible", "cause": "aucune tuile a 6 voisins sur %s" % board_id}
    place = ["--place", "%s:%d,%d" % (HAARKEN, centre[0], centre[1]),
             "--a-place", "%s:%d,%d" % (VICTIME_HERO_1, ring[0][0], ring[0][1]),
             "--a-place", "%s:%d,%d" % (CIBLE_FINALE, ring[1][0], ring[1][1]),
             "--a-place", "%s:%d,%d" % (VICTIME_HERO_2, ring[2][0], ring[2][1]),
             "--unit-stat", "%s:Health=900000,RemainingHealth=900000" % CIBLE_FINALE]
    rid, _sf, err = P947._build(seed, board_id, [HAARKEN],
                                [VICTIME_HERO_1, CIBLE_FINALE, VICTIME_HERO_2], place, hp="1")
    if rid is None:
        return {"verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        dv = P947._view(rpc, rid, inactive=True)
        ids = {}
        for v in (HAARKEN, VICTIME_HERO_1, CIBLE_FINALE, VICTIME_HERO_2):
            u = P947._by_vis(dv, v)
            if u is None:
                return {"verdict": "indisponible", "cause": "unite absente : %s" % v}
            ids[v] = int(u["id"])
        na = P947._normal_attack_id(dv, ids[HAARKEN])
        if na is None:
            return {"verdict": "indisponible", "cause": "attaque normale introuvable"}
        traits = [u for u in (dv.get("units") or []) if int(u.get("id", -1)) == ids[HAARKEN]]
        traits = (traits[0].get("traits") if traits else None)

        def _capture():
            return {"dec": P947._view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                    "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                    "rng": rpc("dumpRng", {"runnerId": rid}, 30)}

        mon_joueur = (P947._view(rpc, rid).get("currentPlayer")
                      or P947._view(rpc, rid).get("currentPlayerId"))
        paires = [(ids[HAARKEN], ids[VICTIME_HERO_1]),
                  (ids[HAARKEN], ids[VICTIME_HERO_2]),
                  (ids[HAARKEN], ids[CIBLE_FINALE])]
        etapes, cap_degat, tuile_avant = [], None, None
        for i, (att, tgt) in enumerate(paires):
            if i == 2:
                cap_degat = _capture()
                pos = P947._pos(P947._view(rpc, rid, inactive=True), tgt)
                tuile_avant = _tile_status_live(rpc, rid, pos) if pos else None
            res, _hits = P947._attack(rpc, rid, att, tgt, na)
            evs = _events(res, tgt)
            coups, autres = _ventiler(evs)
            etapes.append({"rang": i + 1, "cible": tgt,
                           "coups": [e["amount"] for e in coups],
                           "autres": [(e["amount"], e["effect_type"], e["name"]) for e in autres]})
            if i < 2 and not P947._passer_le_tour(rpc, rid, mon_joueur):
                return {"verdict": "indisponible",
                        "cause": "la main n'est pas revenue apres l'attaque #%d" % (i + 1)}
        # rejeu offline depuis la capture d'AVANT l'attaque #3, MEME flux RNG
        p = P947._replay(cap_degat, board, [paires[2]])
        gate = _port_gate(cap_degat, board, ids[HAARKEN], ids[CIBLE_FINALE])
        trace = _replay_trace(cap_degat, board, [paires[2]])
        if dump:
            _dump({"cap": cap_degat, "bg": rpc("boardGraph", {"runnerId": rid}, 60),
                   "att": ids[HAARKEN], "tgt": ids[CIBLE_FINALE]}, dump)
        n3 = etapes[2]
        port_hits = (p["attacks"][0] or {}).get("per_hit")
        return {"verdict": "mesure",
                "trace_port": trace,
                "traits_natifs_haarken": traits,
                "etapes": etapes,
                "attaque_3": {
                    "natif_coups": n3["coups"],
                    "natif_nb_coups": len(n3["coups"]),
                    "natif_total_coups": sum(n3["coups"]),
                    "natif_autres_canaux": n3["autres"],
                    "port_coups": port_hits,
                    "port_nb_coups": (None if port_hits is None else len(port_hits)),
                    "port_total": (p["attacks"][0] or {}).get("total")},
                "gate_natif_tuile_cible": tuile_avant,
                "gate_port": gate,
                "effets_attaquant_port": p.get("effets_attaquant")}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- bras ISOLATION


def _bras_isolation(rpc, board_id, seed, attaques, verbose, dump=None):
    """Haarken (traits NATIFS) contre UNE cible a gros PV, `attaques` fois de suite. Aucun kill ->
    `HeadClaimer` reste a 0, donc le SEUL canal de coup surnumeraire est `LetTheGalaxyBurn`.
    Chaque attaque est rejouee offline depuis la capture prise JUSTE AVANT elle, avec le meme flux
    RNG : la comparaison est donc coup a coup, jamais un agregat."""
    board, err = P947._sonde_graphe(rpc, board_id, seed)
    if board is None:
        return {"verdict": "indisponible", "cause": err}
    centre, ring = P947._tuile_a_six_voisins(board)
    if centre is None:
        return {"verdict": "indisponible", "cause": "aucune tuile a 6 voisins sur %s" % board_id}
    place = ["--place", "%s:%d,%d" % (HAARKEN, centre[0], centre[1]),
             "--a-place", "%s:%d,%d" % (CIBLE_FINALE, ring[0][0], ring[0][1]),
             "--unit-stat", "%s:Health=900000,RemainingHealth=900000" % CIBLE_FINALE]
    rid, _sf, err = P947._build(seed, board_id, [HAARKEN], [CIBLE_FINALE], place)
    if rid is None:
        return {"verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        dv = P947._view(rpc, rid, inactive=True)
        uh, uc = P947._by_vis(dv, HAARKEN), P947._by_vis(dv, CIBLE_FINALE)
        if uh is None or uc is None:
            return {"verdict": "indisponible", "cause": "unite absente"}
        aid, tid = int(uh["id"]), int(uc["id"])
        na = P947._normal_attack_id(dv, aid)
        if na is None:
            return {"verdict": "indisponible", "cause": "attaque normale introuvable"}
        mon_joueur = dv.get("currentPlayer") or dv.get("currentPlayerId")
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        lignes = []
        for i in range(int(attaques)):
            cap = {"dec": P947._view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                   "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                   "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
            pos = P947._pos(P947._view(rpc, rid, inactive=True), tid)
            tuile = _tile_status_live(rpc, rid, pos) if pos else None
            gate = _port_gate(cap, board, aid, tid)
            res, _h = P947._attack(rpc, rid, aid, tid, na)
            coups, autres = _ventiler(_events(res, tid))
            # LEDGER COMPLET cote port : phase d'arme **+** canal #179. Comparer les coups natifs au
            # seul `last["per_hit"]` fabrique un ecart des qu'un groupe additionnel existe -- c'est
            # exactement le faux ecart dont #949 est ne.
            t = _replay_trace(cap, board, [(aid, tid)])
            led = t["ledger"]
            ph = led["complet_per_hit"]
            lignes.append({"rang": i + 1,
                           "natif_coups": [e["amount"] for e in coups],
                           "natif_nb": len(coups),
                           "natif_autres": [(e["amount"], e["effect_type"], e["tags"])
                                            for e in autres],
                           "port_coups": ph, "port_nb": len(ph),
                           "port_arme": led["arme_per_hit"],
                           "port_additionnels": led["additionnels_per_hit"],
                           "port_hp_delta": led["hp_delta"],
                           "maybe": t["maybe"],
                           # ENTREE du descripteur : `FirstHitInCurrentAttackDamageRange` = le
                           # `HitDamage` BRUT de l'attaque. C'est le scalaire dont le coup derive ;
                           # sans lui, un ecart de magnitude n'est pas decomposable.
                           "gate_entree": [g.get("attack_hit_damage") for g in t["gate"]],
                           "tuile_cible_natif": tuile, "gate_port": gate,
                           "egal": [e["amount"] for e in coups] == [int(x) for x in ph]})
            if dump:
                _dump({"cap": cap, "bg": bg, "att": aid, "tgt": tid,
                       "natif_coups": [e["amount"] for e in coups]},
                      "%s-%d.json" % (dump, i + 1))
            if not P947._passer_le_tour(rpc, rid, mon_joueur):
                lignes[-1]["arret"] = "la main n'est pas revenue"
                break
        nb_diff = sum(1 for l in lignes if not l["egal"])
        return {"verdict": "mesure", "attaques": lignes,
                "divergentes": nb_diff, "n": len(lignes)}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- CLI


def _bras_trace_offline(chemin):
    """Rejoue une capture DUMPEE (`--dump`) sans toucher au harnais : aucun runner monte, aucun RPC.
    C'est ce qui rend l'iteration sur le port GRATUITE en budget partage -- la mesure live n'est
    payee qu'UNE fois."""
    from engine.entities.pathfinding.board import Board
    d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    board = Board(d["bg"]["tiles"], adjacency="native_sym")
    paires = [(int(d["att"]), int(d["tgt"]))]
    return {"verdict": "mesure",
            "gate_avant": _port_gate(d["cap"], board, d["att"], d["tgt"]),
            "trace_port": _replay_trace(d["cap"], board, paires)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", choices=("reproduction", "isolation", "trace-offline"),
                    default="reproduction")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--attaques", type=int, default=6)
    ap.add_argument("--dump", default=None, help="persiste la capture (rejeu OFFLINE, sans runner)")
    ap.add_argument("--capture", default=None, help="rejoue une capture dumpee (bras trace-offline)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.bras == "trace-offline":
        out = _bras_trace_offline(a.capture)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=True))
        return 0 if out.get("verdict") == "mesure" else 1
    rpc = _mkrpc()
    if a.bras == "reproduction":
        out = _bras_reproduction(rpc, a.board, a.seed, a.verbose, a.dump)
    else:
        out = _bras_isolation(rpc, a.board, a.seed, a.attaques, a.verbose, a.dump)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=True))
    return 0 if out.get("verdict") == "mesure" else 1


if __name__ == "__main__":
    raise SystemExit(main())
