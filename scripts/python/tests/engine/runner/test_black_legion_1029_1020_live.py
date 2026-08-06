"""case-bl-1029-1020 : face COMBAT de `Drachnyen` (1029, `blackAbaddon`) et `HeraldOfTheApocalypse`
(1020, `blackHaarken`) -- confront LIVE + discriminants de ciblage.

AVANT ce port, les DEUX ids etaient ABSENTS d'`ABILITY_CLASSES` -> `AbilityHandler.
visit_ActiveAbilityMessage` rendait `ported:False` : 0 degat, 0 effet, AUCUNE erreur. Mesure de la
divergence AVANT (probe_bl_1029_1020_baseline.py, seed 777 / MC1_67) : Herald 8450 + 7713 PV non
infliges sur DEUX unites ; Drachnyen PV du caster non SETES (10038 au lieu de 6480) + attaque normale
jamais dispatchee.

ARBRES PORTES (MIRROR du decompile, cf. `engine/runner/abilities/blacklegion.py`) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.DrachnyenAbility$$ExecuteBehaviour` =
      op_BitwiseAnd( op_BitwiseAnd(
          ChangeStat(Owner, Position(Health,0), mode 0 SetAbsolute,
                     Min(StatAmount(Owner, Health, MAXIMUM), Direct(ConfigVar(0x1d = hp)))),
          AddEffect(0x5bf = 1471 Drachnyen_ExtraAttack -> Owner, options ZERO) ),
          UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster)) )
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$ExecuteBehaviour` =
      op_Addition x2( AttackWithAttackDamage(Caster, Target + Enemies(Units(TilesBehindInLine(
                          CasterTile, First(SortByDistance(Tiles(Target), CasterTile), 1), {1,1},
                          Get(2))) - Target), MinMaxDamage, Piercing, ConfigConst(0x2f = nrOfHits)),
                      AddEffect(0x403 = 1027 -> les MEMES cibles, options ZERO),
                      TriggerAbility(Enemies(SurroundingUnits(Target, range, includeCenter)),
                                     0x401 = BattleFatigue) )

CE QUE CES TESTS PROUVENT
  (1) LIVE, DEUX geometries dont une a **armure NON NULLE** (`fixedArmor` 1909-2008 des necrons, mesure
      `probe_bl_armor_scan.py`) -- le profil des deux abilities est `Piercing`, il FAUT de l'armure a
      mordre : le port est ROUTE (`ported is True`) et son CIBLAGE == le ciblage live.
  (2) Drachnyen : `set_health` offline == PV live post-cast, **BIT-EXACT** (etage DETERMINISTE, aucun
      RNG, aucun confond de trait) ; effet 1471 pose sur Abaddon des deux cotes ; attaque normale
      dispatchee sur la cible.
  (3) Herald : LIVE frappe EXACTEMENT {cible, ennemi de la tuile DIRECTEMENT DERRIERE} == offline ;
      effet 1027 pose sur ces DEUX unites des deux cotes ; coups offline == `nrOfHits` config.
  (4) A/B offline bit-exact : l'arbre DSL == une sequence directe `execute_ability_attack` (memes
      bornes/profil/percage/rng) -> le port n'introduit AUCUN bug de degat.
  (5) DISCRIMINANTS de ciblage (offline, geometrie DRIVEE) : la 2e cible de Herald est bien l'occupant
      ENNEMI de la tuile de la LIGNE (pas un anneau, pas un allie, pas la 2e tuile derriere) ; le
      SetHealth de Drachnyen est un SET cape (perte quand hp[level] < PV courants, cap a MaxHealth).

TRAIT DE FACTION COMPOSE PAR-DESSUS (hors de ces deux `ExecuteBehaviour`) : les 5 heros Black Legion
portent `LetTheGalaxyBurn` (1058) qui, sur `On(PreAttack)`, arme a 33 % un COUP ADDITIONNEL
(`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`). A l'ecriture de ce
fichier il DESALIGNAIT le per-coup (deux ecarts nommes par `case-61` §6/§4ter : verdict du `Maybe`, et
conso RNG du canal #179) et l'assertion bit-exact etait donc conditionnelle. **Le rebase du 2026-07-28
a ferme les deux** : le port compose maintenant le meme coup additionnel, avec le meme flux -- mesure
sur la geometrie `MC1_67` ou le trait ARME (3 coups par cible des deux cotes, valeurs identiques). Le
per-coup est desormais asserte **inconditionnellement**, et le nombre de coups est asserte en ACCORD
(offline == live) plutot qu'en conformite a `nrOfHits` : figer `== nrOfHits` reviendrait a interdire
au port de composer le trait, ce qu'il fait maintenant a raison.

Drive les positions des 2 camps (`applyAction` ignore propriete et portee). ⚠ NE JAMAIS deplacer le
CASTER pour rien : son activation est consommee et la main passe a l'autre camp -> le cast suivant est
refuse (`actionConsumed:false`, `mutated:false`) ; on ANCRE la geometrie sur sa tuile courante et on ne
bouge que les ennemis. ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine import battle_query
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatPart, StatType
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.blacklegion import DrachnyenAbility, HeraldOfTheApocalypseAbility
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

ABADDON, HAARKEN = "blackAbaddon", "blackHaarken"
ENEMIES = "necroWarden,necroDestroyer,necroOverlord"
DRACHNYEN, HERALD = 1029, 1020
DRACHNYEN_EXTRA_ATTACK = 1471          # EffectType.Drachnyen_ExtraAttack (0x5bf)
HERALD_EFFECT = 1027                   # EffectType.HeraldOfTheApocalypse (0x403)

# (seed, board, hp_target) -- hp_target None => les a-units GARDENT leur armure (`fixedArmor` ~2000),
# c'est la geometrie DISCRIMINANTE pour un profil `Piercing`. hp_target => Armor/FixedArmor = 0.
GEOMETRIES = [
    pytest.param("777", "MC1_67", None, id="armored-MC1_67"),
    pytest.param("31337", "C3_01", "500000", id="flat-C3_01"),
]


# ------------------------------------------------------------------ helpers etat offline

def _find_by_vis(state, vis):
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _team(state, uid):
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _units_of_team(state, team, want_same=True):
    out = []
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive:
            continue
        if (oc.team == team) == want_same:
            out.append(uid)
    return sorted(out)


def _pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _hp_max(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp_max if hc is not None else None


def _stat(state, uid, stat_type, part=StatPart.CURRENT):
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return sc.ctx.stats.get_stat(int(stat_type), int(part)) if sc is not None else None


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _behind_tiles(board, frm, to):
    """`TilesBehindInLine(from, to, settings{1,1}, Get(2))` -> [tuile `to`, tuile derriere]."""
    return battle_query.get_tiles_behind(
        frm, to, max_count=2, check_walkable=True, update_reference=True,
        walkable_at=lambda p: board.walkable(board.id_at(p[0], p[1])),
        elevation_at=lambda p: board.elevation(board.id_at(p[0], p[1])),
        tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)


def _park_far(state, board, keep_ids, center):
    """Deplace toute unite VIVANTE hors `keep_ids` sur une tuile marchable a plus de 4 hex du centre."""
    used = set()
    far = sorted(t for t in board.by_id
                 if board.walkable(t) and hexgeo.distance(board.coord(t), center) > 4)
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t); _set_pos(state, uid, *board.coord(t)); break


# ------------------------------------------------------------------ helpers live

def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _cascade(res):
    out = list(res.get("cascade") or [])
    for a in (res.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _amounts_by_target(cascade, ability_type=None, group=None):
    """Amounts live par cible. `ability_type` filtre sur le tag `Active_Ability_Type` (isole l'attaque
    d'ability du bruit de tuile/passifs) ; `group` filtre sur le groupe OUVERT (pile de `kind:group` /
    `kind:finish`, cf. probe_217) pour isoler une sous-attaque nommee (`Loki_NormalAttack`)."""
    out, stack = {}, []
    for ev in cascade:
        k = ev.get("kind")
        if k == "group":
            stack.append(ev.get("source")); continue
        if k == "finish":
            if stack:
                stack.pop()
            continue
        t = _tags(ev)
        if "Amount" not in t or t.get("Target_Id") is None:
            continue
        if ability_type is not None and t.get("Active_Ability_Type") != ability_type:
            continue
        if group is not None and group not in stack:
            continue
        out.setdefault(t["Target_Id"], []).append(t["Amount"])
    return out


def _group_sources(cascade):
    return [ev.get("source") for ev in cascade if ev.get("kind") == "group"]


class _Live:
    """Petit driver RPC scope-runner (evite de retrainer `rpc`/`rid` dans 8 signatures)."""

    def __init__(self, rpc, rid):
        self.rpc, self.rid = rpc, rid

    def dv(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "allAbilities": True, "maxRank": 1}, 150)

    def alive(self, dec=None):
        dec = dec if dec is not None else self.dv()
        return [u for u in (dec.get("units") or []) if u.get("alive")]

    def move(self, uid, coord):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 90)

    def endturn(self):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 60)

    def cast(self, caster, target, ability):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": target, "abilityType": ability}}, 240)

    def my_turn(self, owner, tries=12):
        for _ in range(tries):
            dec = self.dv()
            if dec.get("currentPlayer") == owner:
                return dec
            self.endturn()
        return None


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _capture(live, board):
    dec = live.dv()
    ob = live.rpc("observeBattle", {"runnerId": live.rid}, 60)
    snap = live.rpc("combatSnapshot", {"runnerId": live.rid}, 60)
    rng0 = live.rpc("dumpRng", {"runnerId": live.rid}, 30)

    def build_state():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st
    return dec, build_state


def _mk_runner(build_runner, rpc, seed, board_id, hp_target):
    # Confonds NEUTRALISES AU BUILD (#419-r6). Ce fichier confronte des coups a des BORNES
    # (`live t77 [5200, 2461]` contre la borne haute du port) : un crit sort de la plage par
    # construction et fait rougir un port pourtant juste -- mesure, le 1er coup live valait 5200
    # pour une borne haute de 2592. Les QUATRE faces (`--crit`/`--block-player` n'epinglent que
    # les p-units, `--crit-target`/`--block-target` que les a-units).
    extra = ["--p-units", f"{ABADDON},{HAARKEN}", "--a-units", ENEMIES, "--board", board_id,
             "--crit", "0,0", "--crit-target", "0,0",
             "--block-target", "0,0", "--block-player", "0,0"]
    if hp_target:
        extra += ["--hp-target", hp_target]
    rid = build_runner(seed, extra=extra)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispo -- rien n'a ete confronte"
    return rid, Board(bg["tiles"], adjacency="native_sym")


# =================================================================== (1)(2) DRACHNYEN live

@pytest.mark.parametrize("seed,board_id,hp_target", GEOMETRIES)
def test_drachnyen_live_set_health_effect_and_normal_attack(live_session, rpc, build_runner,
                                                            seed, board_id, hp_target):
    """LIVE : le cast 1029 est ROUTE par le port, son etage DETERMINISTE (SetHealth) est BIT-EXACT vs
    live, l'effet 1471 est pose sur Abaddon des deux cotes, et l'attaque NORMALE est dispatchee sur la
    cible. Geometrie ANCREE sur la tuile du caster (le deplacer consommerait son activation)."""
    rid, board = _mk_runner(build_runner, rpc, seed, board_id, hp_target)
    live = _Live(rpc, rid)

    dec = live.dv()
    ab = next((u for u in live.alive(dec) if u.get("visualId") == ABADDON), None)
    assert ab is not None, f"{ABADDON} absent du build"
    dec = live.my_turn(ab.get("owner"))
    assert dec is not None, "jamais mon tour"
    ab = next(u for u in live.alive(dec) if u["id"] == ab["id"])
    ens = [u for u in live.alive(dec) if u.get("owner") != ab.get("owner")]
    assert len(ens) >= 1, "au moins 1 ennemi requis"

    # geometrie : ennemi sur un voisin LIBRE de la tuile COURANTE d'Abaddon (melee)
    C = _upos(ab)
    occ = {_upos(u) for u in live.alive(dec)} - {C}
    nb = [board.coord(t) for t in sorted(board.by_id)
          if board.walkable(t) and hexgeo.distance(board.coord(t), C) == 1
          and board.coord(t) not in occ]
    assert nb, f"aucun voisin libre autour de {C} -- geometrie melee non montable"
    tgt_id = ens[0]["id"]
    live.move(tgt_id, nb[0])

    dec, build_state = _capture(live, board)
    ab = next(u for u in live.alive(dec) if u["id"] == ab["id"])
    tgt = next((u for u in live.alive(dec) if u["id"] == tgt_id), None)
    assert tgt is not None and hexgeo.distance(_upos(ab), _upos(tgt)) == 1, \
        f"cible non adjacente : {_upos(ab)} vs {_upos(tgt) if tgt else None}"
    pre_hp = {u["id"]: u.get("hp") for u in live.alive(dec)}

    # --- OFFLINE (etat PRE-cast, rng cale) ---
    st = build_state()
    armor = _stat(st, tgt_id, StatType.FIXED_ARMOR)
    if hp_target is None:
        assert armor and armor > 0, f"geometrie 'armored' sans armure (fixedArmor={armor})"
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=ab["id"], target_id=tgt_id, ability_type=DRACHNYEN))
    last = runner.ability_handler.last or {}
    assert last.get("ported") is True, f"1029 non routee par le registre de combat : {last}"
    off_set = (last.get("set_health") or {}).get("hp")
    off_eff = last.get("effect") or {}
    off_atk = last.get("attack") or {}
    off_caster_hp = _hp(st, ab["id"])
    off_tgt_hp = _hp(st, tgt_id)

    # --- LIVE ---
    res = live.cast(ab["id"], tgt_id, DRACHNYEN)
    a0 = (res.get("actions") or [{}])[0]
    assert a0.get("ok"), f"cast 1029 KO live : {json.dumps(a0)[:400]}"
    casc = _cascade(res)
    # cf. le test Herald : un cast REFUSE rend une cascade vide (2 events) ; `mutated` n'est pas fiable.
    assert len(casc) > 2, (f"cast 1029 sans cascade -- gate de cible ? "
                           f"actionConsumed={a0.get('actionConsumed')} groupes={_group_sources(casc)}")
    dec2 = live.dv()
    post = {u["id"]: u.get("hp") for u in (dec2.get("units") or [])}
    live_caster_hp = post.get(ab["id"])
    live_effs = {e.get("effectType") for u in (dec2.get("units") or []) if u["id"] == ab["id"]
                 for e in (u.get("effects") or [])}
    normal = _amounts_by_target(casc, group="Loki_NormalAttack")

    print(f"\n[BL1029 {board_id}] armor(cible)={armor} groupes={_group_sources(casc)[:6]}")
    print(f"[BL1029 {board_id}] SetHealth offline={off_set} live={pre_hp.get(ab['id'])} -> {live_caster_hp}")
    print(f"[BL1029 {board_id}] normal-attack live={normal} offline_total={(off_atk.get('attack') or {}).get('total')}")

    # (a) ETAGE DETERMINISTE : le SET de PV est bit-exact (aucun RNG, aucun confond de trait)
    assert off_set is not None and off_caster_hp == off_set, "SetHealth offline non applique"
    assert live_caster_hp == off_set, \
        f"SetHealth : offline {off_set} != live {live_caster_hp} (pre {pre_hp.get(ab['id'])})"
    # le montant EST `Min(MaxHealth, hp[level])` (mirror `Min(StatAmount(Owner,Health,MAX), Direct(hp))`)
    assert off_set == min(int(_hp_max(build_state(), ab["id"])), int(last["hp_amount"])), \
        f"SetHealth {off_set} != Min(MaxHealth, hp[level]={last['hp_amount']})"

    # (b) effet 1471 pose SUR ABADDON des deux cotes (targets = Owner@0x148, source null -> la cible)
    assert off_eff.get("effect_type") == DRACHNYEN_EXTRA_ATTACK and off_eff.get("target") == ab["id"] \
        and off_eff.get("placed"), f"effet 1471 offline non pose sur le caster : {off_eff}"
    assert DRACHNYEN_EXTRA_ATTACK in live_effs, \
        f"effet 1471 absent d'Abaddon live apres cast : {sorted(live_effs)}"

    # (c) l'attaque NORMALE est dispatchee sur la cible des deux cotes
    assert off_atk.get("target") == tgt_id and (off_atk.get("attack") or {}).get("total"), \
        f"attaque normale offline non dispatchee : {off_atk}"
    assert off_tgt_hp is not None and off_tgt_hp < pre_hp[tgt_id], "cible offline non endommagee"
    assert normal.get(tgt_id), f"aucun coup live sous le groupe Loki_NormalAttack : {normal}"


# =================================================================== (1)(3) HERALD live

@pytest.mark.parametrize("seed,board_id,hp_target", GEOMETRIES)
def test_herald_live_targets_line_and_effect(live_session, rpc, build_runner,
                                             seed, board_id, hp_target):
    """LIVE : le cast 1020 frappe EXACTEMENT {cible, ennemi de la tuile DIRECTEMENT DERRIERE} == le
    ciblage offline, pose l'effet 1027 sur ces deux unites des deux cotes, et le port tire `nrOfHits`
    coups par cible (live >= nrOfHits : +1 coup possible via LetTheGalaxyBurn, cf. en-tete)."""
    rid, board = _mk_runner(build_runner, rpc, seed, board_id, hp_target)
    live = _Live(rpc, rid)

    dec = live.dv()
    ha = next((u for u in live.alive(dec) if u.get("visualId") == HAARKEN), None)
    assert ha is not None, f"{HAARKEN} absent du build"
    dec = live.my_turn(ha.get("owner"))
    assert dec is not None, "jamais mon tour"
    ha = next(u for u in live.alive(dec) if u["id"] == ha["id"])
    ens = [u for u in live.alive(dec) if u.get("owner") != ha.get("owner")]
    assert len(ens) >= 2, "au moins 2 ennemis requis (cible + derriere)"

    # geometrie ANCREE sur la tuile du caster : T adjacent, B sur la tuile DERRIERE T dans l'axe C->T
    C = _upos(ha)
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    cset = set(coords)
    plan = None
    for T in [c for c in coords if hexgeo.distance(c, C) == 1]:
        line = _behind_tiles(board, C, T)
        if len(line) >= 2 and line[0] == T and line[1] in cset and line[1] != C:
            plan = (T, line[1]); break
    assert plan is not None, f"aucune ligne C->T->derriere depuis {C} sur {board_id}"
    T, B = plan
    t_id, b_id = ens[0]["id"], ens[1]["id"]
    live.move(t_id, T); live.move(b_id, B)
    # ECARTER Abaddon : son passif `FirstAmongTraitors` est une AURA (+Damage aux allies Chaos a <= 2
    # hex, croissante avec ses attaques) -- un confond de DEGAT non lie a 1020 (cf. memoire
    # « aura = unexplained stat delta »). On le pousse hors de portee pour que le per-coup soit lisible.
    ab = next((u for u in live.alive() if u.get("visualId") == ABADDON), None)
    if ab is not None:
        occ = {_upos(u) for u in live.alive()}
        far = next((board.coord(t) for t in sorted(board.by_id)
                    if board.walkable(t) and board.coord(t) not in occ
                    and hexgeo.distance(board.coord(t), C) > 4), None)
        if far is not None:
            live.move(ab["id"], far)

    dec, build_state = _capture(live, board)
    ha = next(u for u in live.alive(dec) if u["id"] == ha["id"])
    posmap = {u["id"]: _upos(u) for u in live.alive(dec)}
    assert posmap.get(t_id) == T and posmap.get(b_id) == B, \
        f"geometrie non atteinte : C={C} T={T}->{posmap.get(t_id)} B={B}->{posmap.get(b_id)}"
    pre_hp = {u["id"]: u.get("hp") for u in live.alive(dec)}

    # --- OFFLINE (etat PRE-cast, rng cale) ---
    st = build_state()
    armor = _stat(st, t_id, StatType.FIXED_ARMOR)
    if hp_target is None:
        assert armor and armor > 0, f"geometrie 'armored' sans armure (fixedArmor={armor})"
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=ha["id"], target_id=t_id, ability_type=HERALD))
    last = runner.ability_handler.last or {}
    assert last.get("ported") is True, f"1020 non routee par le registre de combat : {last}"
    off_targets = sorted(last.get("targets") or [])
    off_effects = sorted(last.get("effects") or [])
    # #227 : la SEQUENCE d'evenements de degat encaissee par une cible = les coups d'ARME **puis**
    #   les coups des groupes du canal #179 (sous-operations executees APRES la boucle d'arme, dans
    #   la MEME `IdunBattle.Operations.AttackDamageOperation$$Execute`). Le coup `LetTheGalaxyBurn`
    #   est desormais l'un de ces groupes (son artefact natif est un descripteur
    #   `IdunBattle.Entities.Effects.EffectAdditionalHits`, cf. `LetTheGalaxyBurnEffect`), et non
    #   plus un coup d'arme surnumeraire -> il faut concatener les deux canaux pour reconstituer ce
    #   que le live emet. La VALEUR et la position dans le flux RNG sont inchangees sur CE vecteur
    #   (AttackData a `HitDamage` NON degenere -> le groupe tire dans les memes bornes brutes).
    off_per_hit = {a["target"]: (list(a.get("per_hit") or [])
                                 + list((a.get("additional_hits") or {}).get("per_hit") or []))
                   for a in (last.get("attacks") or [])}
    off_hits = {t: len(v) for t, v in off_per_hit.items()}
    # plage NON-CRIT par COUP telle que la calcule le pipeline porte (bornes config-scalees APRES
    # percage/armure) : c'est l'oracle de MAGNITUDE, seule quantite comparable au live malgre le
    # desalignement de flux RNG (cf. en-tete).
    off_band = {a["target"]: (a["clean_min"] // max(1, len(a["per_hit"] or [1])),
                              a["clean_max"] // max(1, len(a["per_hit"] or [1])))
                for a in (last.get("attacks") or []) if a.get("clean_min") is not None}

    import gameconfig as GC
    cfg_hits = int(((GC.ability("HeraldOfTheApocalypse") or {}).get("constants") or {}).get("nrOfHits"))

    # --- LIVE ---
    res = live.cast(ha["id"], t_id, HERALD)
    a0 = (res.get("actions") or [{}])[0]
    assert a0.get("ok"), f"cast 1020 KO live : {json.dumps(a0)[:400]}"
    casc = _cascade(res)
    by_tgt = _amounts_by_target(casc, ability_type=HERALD)
    # Un cast REFUSE par le gate de cible rend une cascade VIDE (`eventCount:2`, un group + un finish,
    # `actionConsumed:false`) -- c'est CA le signal, pas le flag `mutated` (faux negatif : il reste
    # `false` sur des casts qui ont bel et bien mute l'etat).
    assert by_tgt, (f"cast 1020 sans aucun degat live -- gate de cible ? "
                    f"actionConsumed={a0.get('actionConsumed')} eventCount={a0.get('eventCount')} "
                    f"groupes={_group_sources(casc)[:8]}")
    dec2 = live.dv()
    live_eff = sorted(u["id"] for u in (dec2.get("units") or [])
                      if any(e.get("effectType") == HERALD_EFFECT for e in (u.get("effects") or [])))

    print(f"\n[BL1020 {board_id}] C={C} T={T}(t{t_id}) B={B}(t{b_id}) armor(cible)={armor}")
    print(f"[BL1020 {board_id}] offline targets={off_targets} per_hit={off_per_hit} (config nrOfHits={cfg_hits})")
    print(f"[BL1020 {board_id}] live amounts(1020)={by_tgt} effets1027 live={live_eff}")
    exact = all(off_per_hit.get(u) == by_tgt.get(u) for u in by_tgt)
    print(f"[BL1020 {board_id}] plage non-crit par coup (port)={off_band}")
    print(f"[BL1020 {board_id}] per-coup offline-vs-live : {'BIT-EXACT' if exact else 'diff (LetTheGalaxyBurn / canal #179, cf. en-tete + case-61)'}")

    # (a) CIBLAGE : live frappe EXACTEMENT {cible, ennemi derriere} == offline (non confondu)
    assert off_targets == sorted([t_id, b_id]), \
        f"offline frappe {off_targets} != {{t{t_id} (cible), t{b_id} (derriere)}}"
    assert sorted(by_tgt) == sorted([t_id, b_id]), \
        f"live frappe {sorted(by_tgt)} != {{t{t_id}, t{b_id}}}"
    # (b) NOMBRE DE COUPS -- assertion d'ACCORD, pas de conformite a la config. Le port compose
    #   desormais lui aussi le coup additionnel `LetTheGalaxyBurn` (trait de faction, hors de cet
    #   `ExecuteBehaviour`) : exiger `== nrOfHits` reviendrait a figer « le port ignore le trait ».
    #   On exige donc offline == live PAR CIBLE, et au moins la base config des deux cotes.
    assert off_hits == {u: len(v) for u, v in by_tgt.items()}, \
        f"coups offline {off_hits} != live {{u: len(v) for u, v in by_tgt.items()}}"
    for uid, amounts in by_tgt.items():
        assert len(amounts) >= cfg_hits, f"live t{uid} {len(amounts)} coups < config {cfg_hits}"
    # (b-ter) PER-COUP BIT-EXACT, INCONDITIONNEL -- c'est LE critere de la tache : « le degat encaisse
    #   par chaque unite touchee colle-t-il au LIVE ? ». Il l'est sur les DEUX geometries, coup par coup,
    #   Y COMPRIS celle ou `LetTheGalaxyBurn` arme son coup additionnel :
    #       (777, MC1_67, armure 2008) offline {77:[1738,1979,1846], 79:[1805,1632,1536]} == live
    #       (31337, C3_01, armure 0)   offline {77:[1952,2465],      79:[2435,2195]}      == live
    #   L'assertion etait CONDITIONNELLE a l'ecriture de ce fichier (le port ne composait pas encore le
    #   coup du trait, cf. `case-61` §6/§4ter) ; le rebase du 2026-07-28 a ferme cet ecart et le gate a
    #   ete retire. Ne PAS le remettre : c'est cette assertion qui garde l'alignement du flux `state.rng`
    #   sur le vecteur ability des porteurs Black Legion.
    assert off_per_hit == by_tgt, \
        f"per-coup offline {off_per_hit} != live {by_tgt} (flux state.rng desaligne)"
    # (b-bis) MAGNITUDE : la plage NON-CRIT par coup du port (bornes `minDmg`/`maxDmg` config au niveau
    #   et au multiplicateur de rarete du caster, profil Piercing) doit CONTENIR les coups live. C'est le
    #   seul oracle de degat comparable malgre le desalignement de flux RNG -- et il est discriminant :
    #   un mauvais profil, un mauvais niveau/multiplicateur ou un mauvais `nrOfHits` en sortirait.
    #   Armure NON NULLE -> la reduction s'applique APRES le tirage (roll-then-reduce) : seule la borne
    #   HAUTE reste valide des deux cotes.
    for uid, amounts in by_tgt.items():
        lo, hi = off_band[uid]
        assert max(amounts) <= hi, f"live t{uid} {amounts} depasse la borne haute du port {hi}"
        assert min(amounts) > 0, f"live t{uid} {amounts} : coup nul"
        if hp_target:                                  # armure 0 -> plage pleine valide des deux cotes
            assert min(amounts) >= lo, f"live t{uid} {amounts} sous la borne basse du port {lo}"
            assert min(off_per_hit[uid]) >= lo and max(off_per_hit[uid]) <= hi, \
                f"offline t{uid} {off_per_hit[uid]} hors plage [{lo},{hi}]"
    # (c) effet 1027 sur les DEUX cibles, des deux cotes
    assert off_effects == sorted([t_id, b_id]), f"effets 1027 offline {off_effects}"
    assert set([t_id, b_id]) <= set(live_eff), f"effets 1027 live sur {live_eff}"
    # (d) les deux cibles ont bien PERDU des PV offline
    st_hp = {uid: _hp(st, uid) for uid in (t_id, b_id)}
    for uid in (t_id, b_id):
        assert st_hp[uid] < pre_hp[uid], f"t{uid} non endommagee offline ({pre_hp[uid]} -> {st_hp[uid]})"


# =================================================================== (4)(5) offline : A/B + discriminants

@pytest.fixture(scope="module")
def bl_off(rpc, build_runner):
    """Etat LIVE reel (Abaddon + Haarken + 3 necrons, ARMURE INTACTE) charge offline, rejouable a
    volonte : support des discriminants de ciblage (positions DRIVEES en memoire)."""
    rid, board = _mk_runner(build_runner, rpc, "777", "MC1_67", None)
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st
    assert _find_by_vis(build_state(), HAARKEN) is not None, "Haarken absent du build"
    return {"build_state": build_state, "board": board}


def _herald_geometry(board):
    """(C, T, B, D) marchables : dist(C,T)=1, B = tuile DERRIERE T dans l'axe C->T, D = un voisin de T
    qui n'est NI C NI B (anneau autour de la cible, mais HORS ligne) -> discriminant ligne vs anneau."""
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    cset = set(coords)
    for C in coords:
        for T in [c for c in coords if hexgeo.distance(c, C) == 1]:
            line = _behind_tiles(board, C, T)
            if len(line) < 2 or line[0] != T or line[1] not in cset or line[1] == C:
                continue
            B = line[1]
            for D in [c for c in coords if hexgeo.distance(c, T) == 1 and c not in (C, B, T)]:
                return C, T, B, D
    return None


def _place(state, board, caster, mapping, center):
    _park_far(state, board, set(mapping) | {caster}, center)
    for uid, coord in mapping.items():
        _set_pos(state, uid, *coord)


def test_herald_second_target_is_the_line_not_the_ring(bl_off):
    """DISCRIMINANT : la 2e cible est l'occupant de la tuile de la LIGNE (`TilesBehindInLine(CasterTile
    -> tuile cible, maxCount=2)`), PAS un voisin quelconque de la cible. Un ennemi en D (adjacent a la
    cible, hors ligne) n'est PAS touche ; celui en B (derriere) l'est."""
    st = bl_off["build_state"](); board = bl_off["board"]
    ha = _find_by_vis(st, HAARKEN)
    ens = _units_of_team(st, _team(st, ha), want_same=False)
    assert ha is not None and len(ens) >= 3, "Haarken + 3 ennemis requis"
    geom = _herald_geometry(board)
    assert geom is not None, "aucune geometrie ligne/anneau discriminante sur ce board"
    C, T, B, D = geom
    t_id, b_id, d_id = ens[0], ens[1], ens[2]
    _place(st, board, ha, {ha: C, t_id: T, b_id: B, d_id: D}, C)
    hp0 = {u: _hp(st, u) for u in (t_id, b_id, d_id)}

    res = HeraldOfTheApocalypseAbility().execute_behaviour(st, ha, t_id)
    assert res is not None and res.get("dsl") is True, f"port non execute : {res}"
    print(f"\n[BL1020 line] C={C} T={T}(t{t_id}) B={B}(t{b_id}) D={D}(t{d_id}) -> {res['targets']}")
    assert sorted(res["targets"]) == sorted([t_id, b_id]), \
        f"cibles {res['targets']} != {{t{t_id} (cible), t{b_id} (ligne)}}"
    assert _hp(st, d_id) == hp0[d_id], \
        f"t{d_id} (voisin HORS ligne) touche a tort -> ciblage en ANNEAU, pas en ligne"
    assert _hp(st, b_id) < hp0[b_id], f"t{b_id} (tuile derriere) non touche"


def test_herald_behind_must_be_an_enemy(bl_off):
    """DISCRIMINANT `Enemies(Owner@0x148, ...)` : un ALLIE du caster sur la tuile derriere la cible
    n'est PAS frappe -> une seule cible. Refute un `Units(line) - Target` non filtre par equipe."""
    st = bl_off["build_state"](); board = bl_off["board"]
    ha = _find_by_vis(st, HAARKEN)
    ab = _find_by_vis(st, ABADDON)
    ens = _units_of_team(st, _team(st, ha), want_same=False)
    assert ha is not None and ab is not None and ens, "Haarken + Abaddon + 1 ennemi requis"
    geom = _herald_geometry(board)
    assert geom is not None
    C, T, B, _D = geom
    t_id = ens[0]
    _place(st, board, ha, {ha: C, t_id: T, ab: B}, C)          # ALLIE (Abaddon) derriere la cible
    hp0 = {ab: _hp(st, ab), t_id: _hp(st, t_id)}

    res = HeraldOfTheApocalypseAbility().execute_behaviour(st, ha, t_id)
    assert res is not None
    print(f"\n[BL1020 ally-behind] C={C} T={T}(t{t_id}) B={B}(ALLIE t{ab}) -> {res['targets']}")
    assert res["targets"] == [t_id], f"cibles {res['targets']} != [t{t_id}] (l'allie derriere est exclu)"
    assert _hp(st, ab) == hp0[ab], f"l'ALLIE derriere la cible est touche a tort (hp {hp0[ab]})"
    assert res["effects"] == [t_id], f"effet 1027 pose sur {res['effects']} (doit suivre les cibles)"


def test_herald_no_one_behind_is_single_target(bl_off):
    """La tuile derriere est VIDE -> une seule cible (`Units(line)` ne rend que la cible, `- Target()`
    la retire, `Enemies` rend vide) et l'attaque reste mono-cible."""
    st = bl_off["build_state"](); board = bl_off["board"]
    ha = _find_by_vis(st, HAARKEN)
    ens = _units_of_team(st, _team(st, ha), want_same=False)
    geom = _herald_geometry(board)
    assert ha is not None and ens and geom is not None
    C, T, _B, _D = geom
    t_id = ens[0]
    _place(st, board, ha, {ha: C, t_id: T}, C)                 # personne derriere
    res = HeraldOfTheApocalypseAbility().execute_behaviour(st, ha, t_id)
    assert res is not None
    print(f"\n[BL1020 empty-behind] C={C} T={T}(t{t_id}) -> {res['targets']}")
    assert res["targets"] == [t_id], f"cibles {res['targets']} != [t{t_id}]"


def test_herald_tree_equals_direct_attack_baseline(bl_off):
    """A/B OFFLINE bit-exact : l'arbre DSL == une sequence directe `execute_ability_attack` (memes
    bornes config-scalees / profil Piercing / percage / `state.rng` seede, cibles triees par id) ->
    le port n'introduit AUCUN bug de degat par-dessus l'Operation deja validee."""
    board = bl_off["board"]
    st = bl_off["build_state"]()
    ha = _find_by_vis(st, HAARKEN)
    ens = _units_of_team(st, _team(st, ha), want_same=False)
    geom = _herald_geometry(board)
    assert ha is not None and len(ens) >= 2 and geom is not None
    C, T, B, _D = geom
    t_id, b_id = ens[0], ens[1]
    _place(st, board, ha, {ha: C, t_id: T, b_id: B}, C)
    res = HeraldOfTheApocalypseAbility().execute_behaviour(st, ha, t_id)
    assert res is not None
    tree_hits = {a["target"]: a["per_hit"] for a in res["attacks"]}

    # baseline : MEME etat, MEME rng, attaques directes dans l'ordre id (== `multi=True`)
    st2 = bl_off["build_state"]()
    _place(st2, board, ha, {ha: C, t_id: T, b_id: B}, C)
    bmin, bmax, pierce, hits = ability_attack_params(st2, ha, "HeraldOfTheApocalypse", "Piercing",
                                                     ranged=False)
    ref = {}
    for uid in sorted([t_id, b_id]):
        atk = AttackDamageOperation.execute_ability_attack(
            st2, ha, uid, bmin, bmax, pierce, hits, damage_profile="Piercing", is_melee=True)
        ref[uid] = (atk or {}).get("per_hit")
    print(f"\n[BL1020 A/B] tree={tree_hits} baseline={ref} (bmin={bmin} bmax={bmax} pierce={pierce} hits={hits})")
    assert tree_hits == ref, f"arbre {tree_hits} != baseline execute_ability_attack {ref}"


def test_drachnyen_set_health_is_a_capped_set_not_a_heal(bl_off):
    """DISCRIMINANT `Min(StatAmount(Owner, Health, MAXIMUM), Direct(hp[level]))` + mode 0 SetAbsolute :
    (a) a PV pleins, si `hp[level] < MaxHealth` le SET fait PERDRE des PV (ce n'est PAS un heal) ;
    (b) le montant ne depasse JAMAIS MaxHealth (« Abaddon cannot be set to higher Health than his
    maximum Health ») -- verifie en abaissant `hp_max` sous `hp[level]`."""
    st = bl_off["build_state"](); board = bl_off["board"]
    ab = _find_by_vis(st, ABADDON)
    ens = _units_of_team(st, _team(st, ab), want_same=False)
    assert ab is not None and ens
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    C = next(c for c in coords if any(hexgeo.distance(c, d) == 1 for d in coords))
    T = next(d for d in coords if hexgeo.distance(C, d) == 1)
    t_id = ens[0]
    _place(st, board, ab, {ab: C, t_id: T}, C)

    hp_max = int(_hp_max(st, ab))
    res = DrachnyenAbility().execute_behaviour(st, ab, t_id)
    assert res is not None and res.get("dsl") is True
    hp_var = int(res["hp_amount"])
    print(f"\n[BL1029 setHealth] hp_max={hp_max} hp[level]={hp_var} -> {res['set_health']}")
    assert res["set_health"]["hp"] == min(hp_max, hp_var)
    if hp_var < hp_max:                        # (a) SET a la baisse : ce n'est PAS un heal
        assert _hp(st, ab) == hp_var < hp_max, "SetHealth n'a pas fait PERDRE de PV"

    # (b) cap MaxHealth : on rabaisse le plafond SOUS `hp[level]` -> le SET est cape
    st2 = bl_off["build_state"]()
    _place(st2, board, ab, {ab: C, t_id: T}, C)
    e = st2.get_entity(ab)
    hc = e.get_component(HealthComponent)
    hc.hp_max = max(1, hp_var // 2)
    hc.hp = hc.hp_max
    st2.get_entity(ab).get_component(StatsComponent).ctx.stats.components[
        int(StatType.HEALTH)].initial = hc.hp_max
    res2 = DrachnyenAbility().execute_behaviour(st2, ab, t_id)
    assert res2 is not None
    print(f"[BL1029 setHealth cap] hp_max={hc.hp_max} hp[level]={hp_var} -> {res2['set_health']}")
    assert res2["set_health"]["hp"] <= hc.hp_max, \
        f"SetHealth {res2['set_health']['hp']} > MaxHealth {hc.hp_max} (cap `Min` non applique)"


def test_herald_battle_fatigue_target_set_is_the_disc_around_the_target(bl_off):
    """`TriggerAbility(Enemies(SurroundingUnits(Target, range, includeCenter=1)), BattleFatigue)` : le
    SET declenche = les ENNEMIS a <= `range` hex de la CIBLE, **cible INCLUSE** (le natif passe
    `includeCenter=1`). Les allies du caster n'y sont pas ; un ennemi hors du disque non plus. Le
    DISPATCH reste non branche (chance de fuite non sourcable offline, cf. `TriggerAbility`)."""
    import gameconfig as GC
    st = bl_off["build_state"](); board = bl_off["board"]
    ha = _find_by_vis(st, HAARKEN)
    ab = _find_by_vis(st, ABADDON)
    ens = _units_of_team(st, _team(st, ha), want_same=False)
    geom = _herald_geometry(board)
    assert ha is not None and ab is not None and len(ens) >= 3 and geom is not None
    C, T, B, D = geom
    rng_const = int(((GC.ability("HeraldOfTheApocalypse") or {}).get("constants") or {}).get("range"))
    t_id, b_id, far_id = ens[0], ens[1], ens[2]
    # `far` = ennemi a plus de `range` hex de la cible -> hors du disque
    far = next(c for c in (board.coord(t) for t in sorted(board.by_id))
               if board.walkable(board.id_at(c[0], c[1])) and hexgeo.distance(c, T) > rng_const
               and c not in (C, T, B, D))
    _place(st, board, ha, {ha: C, t_id: T, b_id: B, far_id: far, ab: D}, C)

    res = HeraldOfTheApocalypseAbility().execute_behaviour(st, ha, t_id)
    assert res is not None
    fat = res.get("fatigue") or {}
    print(f"\n[BL1020 fatigue] range={rng_const} T={T} -> {fat}")
    assert fat.get("ability_type") == 1025, f"TriggeredAbilityType attendu 1025 : {fat}"
    assert t_id in (fat.get("targets") or []), "la CIBLE doit etre dans le disque (includeCenter=1)"
    assert b_id in (fat.get("targets") or []), "l'ennemi derriere (<= range) doit y etre"
    assert far_id not in (fat.get("targets") or []), \
        f"ennemi a plus de {rng_const} hex inclus a tort : {fat.get('targets')}"
    assert ab not in (fat.get("targets") or []), "un ALLIE du caster ne doit jamais y etre (Enemies)"
    assert fat.get("dispatched") is False, \
        "le dispatch BattleFatigue est volontairement non branche (chance de fuite non sourcable)"
