"""case-366-r1 -- MONTAGE LIVE de `1435 PsychicStalk_FriendlyChaosExtraDamage` (3e effet du kit
`PsychicStalk` / TriggeredAbilityType 1179, porteur `thousAhriman` <<Ahriman>>).

CRITERE BINAIRE : << le port AJOUTE au degat des attaques Flame/Psychic des unites CHAOS amies
d'Ahriman exactement le +extraDmg que le natif ajoute, et se TAIT exactement quand le natif se
tait ? >>

Le natif (`IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$
CreateEffectDamageBonusForAttack`, mirror 1:1 lu au decompile) est

    EffectBonus.ForAddition(
          AreFriends(Owner@0x30, Caster@0x48, comparisonType = 0, anyEntity = false)
        & HasTrait(Caster@0x48, 0x7ea = 2026 = Chaos)
        & GetTargetIsOnFireTileCondition()
        & GetAttackHasValidDamageProfileCondition(),
          ConfigVar(8 = extraDmg) )

-> QUATRE gates, et surtout un CANAL different de son voisin `1215` : `ForAddition` alimente
l'ADDITIF ATTAQUANT (pre-percage, par coup), la ou `1215` (`ForPercentIncrease`) alimente le
%-list DEFENSEUR. Les deux se COMPOSENT : l'additif traverse le percage puis est scale UNE fois
par le %-list -- c'est exactement l'ecart de 664 = round(extraDmg[L50] x 1.8 x 1.33) que la
contre-epreuve de `1215` avait mesure sans le porter.

L'ENUMERATION native du slot 0x16 (`CalculateAttackerModifiersForPrediction`) est STATE-WIDE et
n'exclut PAS le porteur (`IdunBattle.Entities.UnitExtensions$$IsFriend` compare deux
`GetCurrentPlayer(...).index` sans ecarter l'egalite -> `IsFriend(x, x)` = VRAI). Le port scinde
donc en DEUX pattes disjointes, que ce probe exerce SEPAREMENT :

  --attacker ahriman     PATTE SELF  : le porteur attaque lui-meme (`create_effect_damage_bonus_
                         for_attack`). C'est le bras que la contre-epreuve de `1215` avait
                         chiffre : live [4253] / port [3589] AVANT ce port.
  --attacker chaos-ally  PATTE AURA  : `thousSorcerer` (Chaos, ThousandSons, arme PSYCHIC r2)
                         attaque -> `create_aura_attack_damage_bonus_for_ally`.
  --attacker imperial    ANTI-TEMOIN : `astraPrimarisPsy` (Imperial, arme PSYCHIC r2) attaque.
                         `HasTrait(Caster, Chaos)` FERME -> `1435` DOIT etre MUET, et seul `1215`
                         contribue. Un montage ou ce bras diverge du bras chaos est un montage
                         faux.

Les quatre epreuves (memes que le probe frere `probe_366_r1_psychic_stalk.py`) :

  E1 -- POSE, cote NATIF : les trois effets (1215/1216/1435) sont-ils sur Ahriman au deploiement ?
  E2 -- BRAS SANS FEU : `GetTargetIsOnFireTileCondition` ferme -> live == port sans aucun bonus.
  E3 -- POSE DU FEU par le NATIF (`PsychicStalk_ApplyFireTileAbility`, normal ranged d'Ahriman).
  E4 -- BRAS AVEC FEU : live vs port, plus QUATRE contre-epreuves offline
          * `port_sans_1435` : l'ecart d'ATTRIBUTION de CET effet ;
          * `port_sans_1215` : l'attribution CROISEE (le voisin, deja porte) ;
          * `port_sans_feu`  : contrefactuel de TUILE (le gate ferme par l'autre bout) ;
          * `port_niveau_ACTIF` : contrefactuel de NIVEAU.
        Plus la DECOMPOSITION PAR ETAGE : `attacker_modifiers().additive` avec / sans `1435`.

Le niveau : `ConfigVar(8)` s'indexe sur `GetAbilityState(effet)`. Le ctor de la classe n'existe
PAS dans les tables (corps mutualise avec `APsychicStalkEffect$$.ctor`, qui prend son
`AbilityOrEffect` en PARAMETRE), donc le baking n'est PAS attribuable statiquement -- exactement
comme pour `1215`. `--passive-level N` DISSOCIE le niveau passif du niveau actif (que la
normalisation met tous deux a 50) : c'est le SEUL regime qui REFUTE << le niveau lu est celui du
PASSIF >>.

⚠ `extraDmg` EST dans `variablesAffectedByRarityBonus` (`['maxDmg', 'extraDmg']`), a la difference
de l'`extraDmgPct` de `1215` : la valeur est SCALEE par le multiplier de rarete
(`extraDmg[L50] = 277`, x180 % = 499 ; `extraDmg[L1] = 5` -> 9).

Usage :
    python probe_366_r1_psychic_stalk_chaos.py --board MC1_67 --seed 31337 --attacker ahriman
    python probe_366_r1_psychic_stalk_chaos.py --board C4_09  --seed 4242 --attacker chaos-ally
    python probe_366_r1_psychic_stalk_chaos.py --attacker imperial            # ANTI-TEMOIN
    python probe_366_r1_psychic_stalk_chaos.py --attacker ahriman --passive-level 1

Consommateur pytest : `tests/engine/runner/test_psychic_stalk_friendly_chaos_live.py`.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

CARRIER = "thousAhriman"        # <<Ahriman>> -- HERO, dans le pool spawnable du rank courant
CHAOS_ALLY = "thousSorcerer"    # Chaos / ThousandSons, arme PSYCHIC r2 -> `1435` TIRE
IMPERIAL_ALLY = "astraPrimarisPsy"   # Imperial, arme PSYCHIC r2 -> `1435` MUET (anti-temoin)
FOE = "necroWarden"             # <<Makhotep>> -- encaisseur ; ses passifs sont retires
ABILITY = "PsychicStalk"
EFFECT = 1435                   # 0x59b -- EffectType PsychicStalk_FriendlyChaosExtraDamage
EFFECT_PCT = 1215               # 0x4bf -- PsychicStalk_ExtraAttackDamage (voisin, deja porte)
EFFECT_VISUAL = 1216            # 0x4c0 -- PsychicStalk_VisualEffect (aucun canal de degat)
FIRE = 5                        # EffectType.Fire -- ce que `PsychicStalk_ApplyFireTile` pose
HP_TARGET = 400000              # la cible SURVIT aux deux tours (+ le DoT de l'hex en feu)
HP_PLAYER = 300000              # Ahriman/l'allie survivent au tour ennemi
BOARD = "MC1_67"
SEED = "31337"

_ALLY_BY_ARM = {"ahriman": IMPERIAL_ALLY,     # bras SELF : le 2e joueur ne tire pas
                "chaos-ally": CHAOS_ALLY,
                "imperial": IMPERIAL_ALLY}


# --------------------------------------------------------------------------- build
def build_args(board: str, ally: str, passive_level: "int | None" = None) -> list:
    """`--unit-stat` sert DEUX leviers, tous deux appliques au BC DEJA normalise :

      * `PassiveAbilities=[]` sur l'ALLIE et sur la CIBLE -- retire les passifs sans rapport
        (`Nightshroud` cote cible = reduction PLATE du degat recu ; les passifs de l'allie
        peuvent consommer du flux MT ou le deplacer). On ne touche PAS a ceux d'Ahriman :
        `PsychicStalk` EST le sujet.
      * `PassiveAbilityLevel=N` sur Ahriman -- DISSOCIE le niveau PASSIF du niveau ACTIF, que la
        normalisation met tous deux a 50. Seul regime capable de REFUTER << `GetAbilityState(effet)`
        rend l'AbilityState du PASSIF >>.
    """
    out = ["--p-units", "%s,%s" % (CARRIER, ally), "--a-units", FOE,
           "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0",
           "--hp-target", str(HP_TARGET), "--hp-player", str(HP_PLAYER),
           "--board", board,
           "--unit-stat", "%s:PassiveAbilities=[]" % ally,
           "--unit-stat", "%s:PassiveAbilities=[]" % FOE]
    if passive_level is not None:
        out += ["--unit-stat", "%s:PassiveAbilityLevel=%d" % (CARRIER, int(passive_level))]
    return out


def _build_subprocess(seed: str, board: str, tag: str, ally: str,
                      passive_level: "int | None" = None) -> int:
    state = _ROOT / "logs" / ("_probe366r1psc-%s-%d.json" % (tag, os.getpid()))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(board, ally, passive_level)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


# --------------------------------------------------------------------------- lecture live
def _unit(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _by_vis(dec, vis):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def _normal(u):
    return next((a for a in ((u or {}).get("abilities") or []) if a.get("kind") == "normal"), None)


def weapon_profile(vis: str, ranged: bool) -> "str | None":
    """`DamageProfile` de l'arme utilisee -- lu au GAMECONFIG (`decisionView.abilities[]` n'expose
    PAS le profil). `ranged` = l'arme portant `Range` ; sinon la premiere (melee)."""
    import gameconfig as GC
    ws = (GC.unit(vis) or {}).get("weapons") or []
    for w in ws:
        if bool(w.get("Range")) == bool(ranged):
            return w.get("DamageProfile")
    return (ws[0].get("DamageProfile") if ws else None)


def live_amounts(res, target_id):
    """Per-coup LIVE attribues a `target_id`, dans l'ordre des events + flag de salete.

    ⚠ ATTRIBUTION PAR CANAL (`Effect_Type`) : la reponse d'une action porte AUSSI les degats qui
    ne viennent PAS de l'attaque mesuree -- typiquement le DoT de l'hex en feu (`Effect_Type = 5`,
    cf. `project_effect_type_attribution`). Les melanger ferait comparer une somme a un coup.
    On rend donc les DEUX listes separement ; seule `hits` est comparable au rejeu offline."""
    hits, other, dirty = [], [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") != target_id or "Amount" not in td:
                continue
            row = (int(td.get("Amount")), td.get("Effect_Type"), td.get("Source_Id"))
            if td.get("Effect_Type") in (None, 0, 1009):      # coup d'attaque (incl. overwatch)
                hits.append(row[0])
                dirty = dirty or bool(td.get("Attack_DidCrit")) \
                    or bool(td.get("Attack_DidBlock")) or bool(td.get("Attack_DidEvade"))
            else:
                other.append(row)
    return hits, dirty, other


def fire_tiles(tm) -> list:
    """Positions (col,row) portant l'effet `Fire` d'apres `tileMeta` -- l'oracle NATIF du gate."""
    return [(t["col"], t["row"]) for t in ((tm or {}).get("tiles") or [])
            if any(e.get("effectType") == FIRE for e in (t.get("effects") or []))]


# --------------------------------------------------------------------------- pilotage
def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                               "captureEvents": False}, 90)


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _place_at_distance(rpc, rid, mover_vis, anchor_vis, want, tries=25):
    """DEPLACE `mover_vis` jusqu'a la distance hex `want` d'`anchor_vis`. On FABRIQUE la geometrie,
    on ne la subit pas (doctrine : jamais << bloque par la geometrie de spawn >>)."""
    import hexgeo
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv, an = _by_vis(dv, mover_vis), _by_vis(dv, anchor_vis)
        if mv is None or an is None:
            return None
        mpos = (mv["pos"]["col"], mv["pos"]["row"])
        apos = (an["pos"]["col"], an["pos"]["row"])
        if hexgeo.distance(mpos, apos) == want:
            return want
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        if not tiles:
            _endturn(rpc, rid)
            continue
        best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, apos) - want),
                                         hexgeo.distance(t, apos)))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": best[0], "row": best[1]}},
            "captureEvents": False}, 90)
        if hexgeo.distance(best, apos) == want:
            return want
        _endturn(rpc, rid)
    return None


def _ensure_turn(rpc, rid, owner, tries=8):
    """Fait tourner les fins de tour jusqu'a ce que `owner` soit le joueur courant."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == owner:
            return dv
        _endturn(rpc, rid)
    return None


# --------------------------------------------------------------------------- offline
def _capture(rpc, rid):
    return {
        "dv": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                            "includeInactive": True}, 150),
        "ob": rpc("observeBattle", {"runnerId": rid}, 90),
        "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
        "tm": rpc("tileMeta", {"runnerId": rid}, 90),
        "rng": rpc("dumpRng", {"runnerId": rid}, 40),
    }


def _load(cap, board):
    """`tiles=` est INDISPENSABLE : sans lui l'etat offline repart d'un plateau VIERGE et le gate
    `GetTargetIsOnFireTileCondition` serait faux pour une raison de HARNAIS, pas de mecanique."""
    from engine.runner.snapshot import load_state
    return load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])


def _strip_effect(st, carrier_id, etype):
    for e in (st.effects.by_unit.get(carrier_id) or []):
        if e.effect_type == etype:
            e.consumed = True


def _strip_fire(st, pos):
    """CONTREFACTUEL de TUILE : eteint l'hex sous la cible dans le monde offline."""
    tid = st.board.id_at(pos[0], pos[1]) if st.board is not None else None
    if tid is None:
        return
    for e in (st.effects.by_unit.get(int(tid)) or []):
        if e.effect_type == FIRE:
            e.consumed = True


def _force_level(st, carrier_id, level, etype=EFFECT):
    """CONTREFACTUEL DE NIVEAU : reindexe `ConfigVar(8)` sur `level`. Sans ce temoin,
    << live == port au niveau PASSIF >> ne prouverait rien si le niveau ACTIF donnait la MEME
    valeur (regime NOMINAL degenere : les deux a 50)."""
    for e in (st.effects.by_unit.get(carrier_id) or []):
        if e.effect_type == etype:
            e.ability_level = level


def offline_hits(cap, board, caster_id, target_id, strip_effect_on=None, strip_effect_type=EFFECT,
                 strip_fire_at=None, force_level_on=None, force_level=None):
    """Rejoue le MEME coup OFFLINE sur la MEME capture et le MEME flux MT -> per-coup du port."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    st = _load(cap, board)
    if strip_effect_on is not None:
        _strip_effect(st, int(strip_effect_on), strip_effect_type)
    if strip_fire_at is not None:
        _strip_fire(st, strip_fire_at)
    if force_level_on is not None and force_level is not None:
        _force_level(st, int(force_level_on), int(force_level))
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    last = getattr(getattr(runner, "damage_handler", None), "last", None)
    return list((last or {}).get("per_hit") or [])


def offline_stage_view(cap, board, att_id, tgt_id, profile, is_ranged, strip_effect_on=None,
                       strip_effect_type=EFFECT):
    """DECOMPOSITION PAR ETAGE (doctrine : jamais fitter un scalaire). Rend l'accumulateur
    `DamageModifiers` **ATTAQUANT** que le port construit pour ce coup, AVANT toute application.
    C'est le SEUL moyen de dire << mon canal a ecrit dans LE bon slot >> : `1435` doit apparaitre
    dans `additive` (`ForAddition`), PAS dans `pct_list` (le slot de son voisin `1215`)."""
    from engine.runner.damage_model import attacker_modifiers, target_trait_names
    st = _load(cap, board)
    if strip_effect_on is not None:
        _strip_effect(st, int(strip_effect_on), strip_effect_type)
    mods, _active = attacker_modifiers(st, att_id, None, is_ranged=is_ranged,
                                       target_traits=target_trait_names(st, tgt_id),
                                       target_id=tgt_id, is_normal_attack=True,
                                       damage_profile=profile)
    return {"pct_list": [[float(m), c] for m, c in (mods.pct_list or [])],
            "additive": int(mods.additive), "flat_reductions": list(mods.flat_reductions or []),
            "armor_penetration": int(getattr(mods, "armor_penetration", 0) or 0)}


def offline_effect_view(cap, board, carrier_id, tgt_id, tgt_pos, att_id, att_team, owner_team,
                        profile):
    """Ce que le PORT materialise pour `1435` sur cette capture : presence, classe, niveau, et le
    bonus rendu dans chaque regime de gate. Etage SEPARE du degat -- un port qui n'aurait PAS
    l'effet et un port dont le gate ferme rendent le meme degat."""
    st = _load(cap, board)
    inst = next((e for e in (st.effects.by_unit.get(carrier_id) or [])
                 if e.effect_type == EFFECT), None)
    if inst is None:
        return {"present": False,
                "effects_on_carrier": [(e.effect_type, e.name)
                                       for e in (st.effects.by_unit.get(carrier_id) or [])]}
    base = {"att_grand_alliance": "Chaos", "damage_profile": profile,
            "t_pos": tuple(tgt_pos), "tile_effects_by_pos": {tuple(tgt_pos): ["Fire"]},
            "owner_id": carrier_id, "owner_team": owner_team,
            "att_id": att_id, "att_team": att_team, "tgt_id": tgt_id}

    def _self(**over):
        eb = inst.create_effect_damage_bonus_for_attack(att_ctx={**base, **over})
        return None if eb is None else [eb.kind, eb.value]

    def _aura(**over):
        eb = inst.create_aura_attack_damage_bonus_for_ally({**base, **over})
        return None if eb is None else [eb.kind, eb.value]

    return {"present": True, "cls": type(inst).__name__,
            "ability_level": inst.ability_level,
            "active_ability_level": inst.active_ability_level,
            "multiplier": inst.ability_variables_multiplier,
            "self_nominal": _self(),                                  # Chaos + feu + profil valide
            "self_no_fire": _self(tile_effects_by_pos={tuple(tgt_pos): ["Ice"]}),
            "self_no_tile_channel": _self(tile_effects_by_pos=None),
            "self_imperial": _self(att_grand_alliance="Imperial"),
            "self_ga_unknown": _self(att_grand_alliance=None),
            "self_profile_physical": _self(damage_profile="Physical"),
            "self_profile_none": _self(damage_profile=None),
            "self_profile_flame": _self(damage_profile="Flame"),
            "aura_nominal": _aura(),
            "aura_enemy_attacker": _aura(att_team=(0 if owner_team else 1)),
            "aura_team_unknown": _aura(att_team=None)}


# --------------------------------------------------------------------------- montage
def run(rpc, seed: str = SEED, board_id: str = BOARD, keep: bool = False,
        attacker: str = "ahriman", passive_level: "int | None" = None) -> dict:
    r = {"seed": seed, "board": board_id, "rid": None, "attacker": attacker,
         "passive_level_forced": passive_level}
    try:
        _run(rpc, r, seed, board_id, attacker, passive_level)
    except Exception as exc:                              # montage KO -> ERREUR, jamais un vert
        r["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if not keep and r.get("rid") is not None:
            try:
                rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
            except Exception:                             # nettoyage best-effort
                pass
    return r


def _attack(rpc, rid, caster, target):
    norm = _normal(caster)
    if norm is None:
        raise RuntimeError("aucune attaque normale exposee sur %s" % (caster.get("visualId"),))
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster["id"], "targetId": target["id"],
        "abilityType": norm["id"]}}, 150)
    if not (isinstance(res, dict) and res.get("ok")):
        raise RuntimeError("coup live KO: %s" % (str(res)[:200],))
    return res


def _run(rpc, r: dict, seed: str, board_id: str, attacker: str,
         passive_level: "int | None") -> None:
    import hexgeo
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    ally_vis = _ALLY_BY_ARM[attacker]
    att_vis = CARRIER if attacker == "ahriman" else ally_vis
    r["attacker_visual"], r["ally_visual"] = att_vis, ally_vis

    rid = _build_subprocess(seed, board_id, attacker, ally_vis, passive_level)
    r["rid"] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    dv0i = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": True}, 150)
    car, ally, foe = _by_vis(dv0, CARRIER), _by_vis(dv0, ally_vis), _by_vis(dv0, FOE)
    if car is None or ally is None or foe is None:
        raise RuntimeError("deploiement incomplet (carrier=%s ally=%s foe=%s)"
                           % (car is not None, ally is not None, foe is not None))
    r["carrier_id"], r["ally_id"], r["foe_id"] = car["id"], ally["id"], foe["id"]
    r["carrier_owner"], r["foe_owner"] = car.get("owner"), foe.get("owner")
    att = car if att_vis == CARRIER else ally
    r["att_id"] = att["id"]

    # -- E1 : POSE des TROIS effets du kit, cote NATIF ----------------------------------------
    r["e1_effects_on_carrier"] = [(e.get("effectType"), e.get("name"), e.get("active"))
                                  for e in ((_unit(dv0i, car["id"]) or {}).get("effects") or [])]
    for tag, etype in (("chaos", EFFECT), ("pct", EFFECT_PCT), ("visual", EFFECT_VISUAL)):
        r["e1_%s_default_channel" % tag] = _eff(_unit(dv0, car["id"]), etype) is not None
        r["e1_%s_inactive_channel" % tag] = _eff(_unit(dv0i, car["id"]), etype) is not None

    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 120)
    _uc0 = next((u.get("unitConfig") or {} for u in (snap0.get("units") or [])
                 if u.get("entityId") == car["id"]), {})
    r["passive_level"] = _uc0.get("passiveAbilityLevel")
    r["active_level"] = _uc0.get("activeAbilityLevel")
    r["multiplier"] = (_uc0.get("abilityVariablesMultiplierPercentage")
                       or _uc0.get("abilityVariablesMultiplier") or 100)
    r["extra_dmg_passive"] = ability_var(ABILITY, "extraDmg", r["passive_level"],
                                         multiplier_pct=r["multiplier"] or 100)
    r["extra_dmg_active"] = ability_var(ABILITY, "extraDmg", r["active_level"],
                                        multiplier_pct=r["multiplier"] or 100)
    r["extra_dmg_pct_passive"] = ability_var(ABILITY, "extraDmgPct", r["passive_level"],
                                             multiplier_pct=r["multiplier"] or 100)

    # ---------------------------------------------------------------- E2 : BRAS SANS FEU
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du joueur non atteint (bras sans feu)")
    if _place_at_distance(rpc, rid, att_vis, FOE, 2) != 2:
        raise RuntimeError("attaquant non place a d=2 (bras sans feu)")
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du joueur non retabli (bras sans feu)")

    capA = _capture(rpc, rid)
    dvA = capA["dv"]
    attA, foeA = _unit(dvA, att["id"]), _unit(dvA, foe["id"])
    fpos_a = (foeA["pos"]["col"], foeA["pos"]["row"])
    r["a_fire_tiles"] = fire_tiles(capA["tm"])
    r["a_target_on_fire"] = fpos_a in r["a_fire_tiles"]
    r["a_dist"] = hexgeo.distance((attA["pos"]["col"], attA["pos"]["row"]), fpos_a)
    r["a_profile"] = weapon_profile(att_vis, ranged=(r["a_dist"] > 1))
    resA = _attack(rpc, rid, attA, foeA)
    hitsA, dirtyA, otherA = live_amounts(resA, foe["id"])
    r["a_live_other_channels"] = otherA
    if not hitsA:
        raise RuntimeError("coup A joue mais aucun degat attribue a la cible")
    r["a_live_hits"], r["a_dirty"] = hitsA, dirtyA
    r["a_port_hits"] = offline_hits(capA, board, att["id"], foe["id"])

    # ---------------------------------------------------------------- E3 : POSE DU FEU
    dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car1, foe1 = _unit(dv1, car["id"]), _unit(dv1, foe["id"])
    if dv1.get("currentPlayer") == car["owner"] and car1 is not None and foe1 is not None:
        if hexgeo.distance((car1["pos"]["col"], car1["pos"]["row"]),
                           (foe1["pos"]["col"], foe1["pos"]["row"])) > 2:
            _place_at_distance(rpc, rid, CARRIER, FOE, 2)
        dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        car1, foe1 = _unit(dv1, car["id"]), _unit(dv1, foe["id"])
        if car1 is not None and foe1 is not None:
            try:
                _attack(rpc, rid, car1, foe1)
            except RuntimeError as exc:
                r["e3_carrier_attack_error"] = str(exc)[:200]
    tm1 = rpc("tileMeta", {"runnerId": rid}, 90)
    dv1b = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    foe1b = _unit(dv1b, foe["id"])
    r["e3_fire_tiles"] = fire_tiles(tm1)
    r["e3_target_on_fire"] = (foe1b is not None
                              and (foe1b["pos"]["col"], foe1b["pos"]["row"]) in r["e3_fire_tiles"])

    # ---------------------------------------------------------------- E4 : BRAS AVEC FEU
    # Tour suivant du joueur : Ahriman RE-pose le feu sous la position COURANTE de la cible (elle
    # a pu bouger), PUIS l'attaquant frappe. L'ordre garantit que l'hex brule au moment du coup.
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du joueur non atteint (bras avec feu)")
    if _place_at_distance(rpc, rid, CARRIER, FOE, 2) != 2:
        raise RuntimeError("Ahriman non place a d=2 pour re-poser le feu")
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du joueur non retabli (re-pose)")
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car2, foe2 = _unit(dv2, car["id"]), _unit(dv2, foe["id"])
    if car2 is None or foe2 is None:
        raise RuntimeError("porteur ou cible mort avant le bras avec feu")
    _attack(rpc, rid, car2, foe2)
    if att_vis != CARRIER:
        if _place_at_distance(rpc, rid, att_vis, FOE, 2) != 2:
            raise RuntimeError("attaquant non place a d=2 (bras avec feu)")
        if _ensure_turn(rpc, rid, car["owner"]) is None:
            raise RuntimeError("tour du joueur non retabli (bras avec feu)")
    else:
        # PATTE SELF : Ahriman doit frapper une SECONDE fois -> il faut son tour suivant.
        for _ in range(4):
            _endturn(rpc, rid)
            dvx = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if dvx.get("currentPlayer") == car["owner"]:
                break
        if _place_at_distance(rpc, rid, CARRIER, FOE, 2) != 2:
            raise RuntimeError("Ahriman non replace a d=2 (patte self)")
        if _ensure_turn(rpc, rid, car["owner"]) is None:
            raise RuntimeError("tour du joueur non retabli (patte self)")

    capB = _capture(rpc, rid)
    dvB = capB["dv"]
    attB, foeB = _unit(dvB, att["id"]), _unit(dvB, foe["id"])
    if attB is None or foeB is None:
        raise RuntimeError("attaquant ou cible absent de la capture B")
    fpos_b = (foeB["pos"]["col"], foeB["pos"]["row"])
    r["b_fire_tiles"] = fire_tiles(capB["tm"])
    r["b_target_on_fire"] = fpos_b in r["b_fire_tiles"]
    r["b_dist"] = hexgeo.distance((attB["pos"]["col"], attB["pos"]["row"]), fpos_b)
    r["b_profile"] = weapon_profile(att_vis, ranged=(r["b_dist"] > 1))
    r["b_port_effect_view"] = offline_effect_view(
        capB, board, car["id"], foe["id"], fpos_b, att["id"],
        attB.get("owner"), car.get("owner"), r["b_profile"])
    if not r["b_target_on_fire"]:
        raise RuntimeError("la cible n'est PAS sur un hex en feu au moment du coup B "
                           "(feu=%s, cible=%s)" % (r["b_fire_tiles"], fpos_b))

    resB = _attack(rpc, rid, attB, foeB)
    hitsB, dirtyB, otherB = live_amounts(resB, foe["id"])
    r["b_live_other_channels"] = otherB
    if not hitsB:
        raise RuntimeError("coup B joue mais aucun degat attribue a la cible")
    r["b_live_hits"], r["b_dirty"] = hitsB, dirtyB
    r["b_port_hits"] = offline_hits(capB, board, att["id"], foe["id"])
    r["b_port_hits_without_1435"] = offline_hits(capB, board, att["id"], foe["id"],
                                                 strip_effect_on=car["id"],
                                                 strip_effect_type=EFFECT)
    r["b_port_hits_without_1215"] = offline_hits(capB, board, att["id"], foe["id"],
                                                 strip_effect_on=car["id"],
                                                 strip_effect_type=EFFECT_PCT)
    r["b_port_hits_without_fire"] = offline_hits(capB, board, att["id"], foe["id"],
                                                 strip_fire_at=fpos_b)
    # CONTREFACTUEL DE NIVEAU : et si `GetAbilityState` rendait l'AbilityState de l'ACTIVE ?
    r["b_port_hits_active_level"] = offline_hits(
        capB, board, att["id"], foe["id"],
        force_level_on=car["id"], force_level=r["active_level"])
    # DECOMPOSITION PAR ETAGE : ou mon canal ecrit-il, exactement ?
    _rng = (r["b_dist"] > 1)
    r["b_stage_with"] = offline_stage_view(capB, board, att["id"], foe["id"], r["b_profile"], _rng)
    r["b_stage_without"] = offline_stage_view(capB, board, att["id"], foe["id"], r["b_profile"],
                                              _rng, strip_effect_on=car["id"],
                                              strip_effect_type=EFFECT)
    r["ok"] = True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--attacker", choices=("ahriman", "chaos-ally", "imperial"),
                    default="ahriman",
                    help="'ahriman'=patte SELF, 'chaos-ally'=patte AURA, 'imperial'=ANTI-TEMOIN")
    ap.add_argument("--passive-level", type=int, default=None,
                    help="force BC.Units.PassiveAbilityLevel d'Ahriman -- DISSOCIE passif/actif")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, seed=a.seed, board_id=a.board, keep=a.keep, attacker=a.attacker,
            passive_level=a.passive_level)
    print(json.dumps(r, indent=1, default=str))
    if r.get("error"):
        return 1
    print("")
    print("[366-r1/1435] runner=%s board=%s seed=%s attaquant=%s (allie=%s)"
          % (r["rid"], a.board, a.seed, r["attacker_visual"], r["ally_visual"]))
    print("  config  : extraDmg[PASSIF L%s] = %s | [ACTIF L%s] = %s (mult %s, DANS rarityBonus)"
          % (r["passive_level"], r["extra_dmg_passive"], r["active_level"],
             r["extra_dmg_active"], r["multiplier"]))
    print("  E1 POSE : 1435 def/inact=%s/%s  1215=%s/%s  1216=%s/%s"
          % (r["e1_chaos_default_channel"], r["e1_chaos_inactive_channel"],
             r["e1_pct_default_channel"], r["e1_pct_inactive_channel"],
             r["e1_visual_default_channel"], r["e1_visual_inactive_channel"]))
    print("  E2 SANS FEU (profil %s, d=%s) : live=%s  port=%s   [feu sous cible: %s]"
          % (r["a_profile"], r["a_dist"], r["a_live_hits"], r["a_port_hits"],
             r["a_target_on_fire"]))
    print("  E3 POSE FEU (natif) : hexes en feu=%s  cible dessus=%s"
          % (r["e3_fire_tiles"], r["e3_target_on_fire"]))
    print("  E4 AVEC FEU (profil %s, d=%s) : live=%s  port=%s"
          % (r["b_profile"], r["b_dist"], r["b_live_hits"], r["b_port_hits"]))
    print("     CONTRE-EPREUVE sans 1435 : %s" % (r["b_port_hits_without_1435"],))
    print("     CONTRE-EPREUVE sans 1215 : %s" % (r["b_port_hits_without_1215"],))
    print("     CONTREFACTUEL sans feu   : %s" % (r["b_port_hits_without_fire"],))
    print("     CONTREFACTUEL niveau ACTIF (L%s) : %s"
          % (r["active_level"], r["b_port_hits_active_level"]))
    print("     ETAGE att_mods AVEC  : %s" % (json.dumps(r["b_stage_with"]),))
    print("     ETAGE att_mods SANS  : %s" % (json.dumps(r["b_stage_without"]),))
    print("  PORT effet (B) : %s" % (json.dumps(r["b_port_effect_view"], default=str),))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
