"""case-231 -- socle `IsCharging` + `force_crit`, confront LIVE des DEUX abilities du lot.

CE QUE CES TESTS GARDENT
------------------------
Deux PRIMITIVES partagees, chacune avec son porteur :

  * **`IsCharging`** (`IdunBattle.Core.Services.BattleQuery$$IsCharging`) =
    `AreEntitiesAdjacent(caster, target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`.
    La liste est ecrite par `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` (unites
    devenues NOUVELLEMENT adjacentes pendant le pas) et videe par
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`.
    ⚠ **Ce n'est PAS `HasMoved`** -- et c'est exactement ce que garde
    `test_tp_charge_nest_pas_has_moved_live` : Titus BOUGE, et pourtant la cible (deja adjacente
    AVANT le pas) n'est pas chargee, donc c'est la branche NON-CHARGE qui tourne.

  * **`force_crit`** = l'octet **+5** du `Nullable<AttackOptions>` (8e argument de
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ; le meme struct dont l'octet +4
    porte `force_overkill` de FlailSwing, ce qui CALE le mapping).
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` SAUTE alors `RollCritical` : le coup
    est critique SANS tirage, **meme a `CouldCrit` faux** (Titus a `CritChance = 0`).

PORTEURS : `TacticalPrecisionAbility` (1154, `ultraTitus`) pour les deux ; `MomentShackleAbility`
(1184, `custoTrajann`) pour le volet heal + les deux `DynamicStatModifierEffect` 1391/1392.

GEOMETRIE : `applyAction {kind: "move"}` du runner **ignore la portee de deplacement** (verifie :
un pas de 6 hexes passe) -> les positions sont POSEES, pas marchees. Chaque tuile est DERIVEE du
`boardGraph` (aucune coordonnee en dur), et l'ORDRE des poses est porteur de sens : on place
Titus D'ABORD (ennemis encore au spawn, loin) pour que son `ChargedUnitIds` reste vide, puis les
ennemis, puis -- pour les cas CHARGE seulement -- le pas final de Titus.

CONFOND ECARTE ET NOMME : les premieres mesures utilisaient `templChampion` comme cible. Son
passif `MartialSuperiority` riposte 2x Power **avant** l'attaque adverse (et son trait `Parry`
retire un coup aux multi-hits melee) -> le flux RNG est decale AVANT le tirage de Titus et le
per-coup n'est plus comparable. Les cibles retenues (`necroWarden`, `astraBullgryn`) n'ont ni
riposte ni reduction de coups. (`necroWarden` porte `LivingMetal`, qui le soigne en debut de
tour : on ne mesure donc QUE le delta d'un cast, jamais a cheval sur une fin de tour.)

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.runner.abilities.custodes import MomentShackleAbility
from engine.runner.abilities.ultramarines import TacticalPrecisionAbility
from engine.runner.components import StatsComponent, UnitComponent
from engine.runner.messages import MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

TITUS = "ultraTitus"            # 1154 TacticalPrecision
TRAJANN = "custoTrajann"        # 1184 MomentShackle
FOES = "necroWarden,astraBullgryn"
#: ⚠ `TITUS:CritChance=0` -- LA PREMISSE DU FICHIER, RECONSTRUITE (#923). Tout ce fichier est ecrit
#: sur « Titus a `CritChance = 0` » (cf. l'en-tete : le coup est critique SANS tirage, MEME a
#: `CouldCrit` faux), et `test_force_crit_change_le_degat_ab_offline` en fait une ASSERTION -- sans
#: quoi son A/B `force_crit=True` vs `False` ne compare plus rien, la branche `False` pouvant crit
#: toute seule. Or cette premisse est une propriete du HARNAIS, pas du jeu : depuis #419-r5/#419-r6
#: `_normalize_and_extract_pool` equipe par defaut les items Best-In-Slot, et les quatre stats
#: crit/block ne vivent QUE dans les items -> `ultraTitus` arrive a 26. QUATRIEME peremption de
#: premisse due a ce meme changement de regime.
#: VOIE RETENUE = reconstruire LE PORTEUR, precedent #914/#912 deja applique par
#: `probe_373_path_of_command_extra_crit.py`. PAS `TACTICUS_BIS_ITEMS=0`, qui deshabillerait tout
#: le roster et changerait le regime des DEUX equipes (dont `critDamage`) : on veut le regime
#: COURANT avec un porteur a crit nul, pas l'ancien regime.
BUILD = ["--p-units", "%s,%s" % (TITUS, TRAJANN), "--a-units", FOES, "--rank", "17", "--no-ai",
         "--unit-stat", "%s:CritChance=0" % (TITUS,)]
TP = 1154
MS = 1184


# --------------------------------------------------------------------------- helpers

def _units(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv, vis):
    return next((u for u in _units(dv) if u.get("visualId") == vis), None)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _hp_live(ob):
    """PV live par id : `observeBattle.units` porte `squadId` (l'id du decisionView / du port) et
    `entityId` (l'entite ECS) -- se tromper de cle ne recoupe AUCUNE ligne offline."""
    return {int(u["squadId"]): int(u.get("hp") or 0)
            for u in (ob.get("units") or []) if u.get("squadId") is not None}


def _hp_off(state, ids):
    from engine.runner.components import HealthComponent
    out = {}
    for uid in ids:
        e = state.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        out[uid] = int(hc.hp or 0) if hc is not None else 0
    return out


def _seed(state, dump):
    if isinstance(dump, dict) and dump.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(dump["mt"])
        r.mti = dump["mti"]
        state.rng = r
    return state


class Arena:
    """Bataille LIVE isolee + son miroir offline rechargeable a volonte. FIXTURE NOMMEE (le
    montage geometrique est le meme pour les quatre scenarios, seul l'ORDRE des poses change)."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board

    # -- live
    def dv(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "maxRank": 1,
                                         "allAbilities": True}, 90)

    def ob(self):
        return self.rpc("observeBattle", {"runnerId": self.rid}, 40)

    def act(self, action, timeout=60):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": action}, timeout)

    def place(self, uid, coord):
        """`applyAction move` IGNORE la portee de deplacement (mesure) : on POSE l'unite.

        ⚠ Il rend `ok=True` MEME quand le pas est refuse (tuile occupee, non marchable) et l'unite
        reste ou elle est. On RELIT donc la position : sans cette verification le montage se fait a
        moitie, les deux camps ne sont pas la ou on croit, et le test compare deux etats qui n'ont
        rien a voir -- en rendant VERT ce qui devrait etre rouge (vecu sur cette meme fixture)."""
        self.act({"kind": "move", "unitId": uid,
                  "to": {"col": coord[0], "row": coord[1]}}, 40)
        got = next((_pos(u) for u in _units(self.dv()) if u.get("id") == uid), None)
        assert got == tuple(coord), (
            "pose refusee : u%s voulu %s, obtenu %s (tuile occupee / non marchable ?)"
            % (uid, tuple(coord), got))

    def cast(self, caster, target, ability):
        """L'enveloppe `ok` du RPC vaut True MEME quand l'action a ete refusee : le verdict reel est
        `actions[0]`. Ne pas descendre d'un cran rend un test VERT sur un cast qui n'a jamais eu lieu
        (vecu : trois scenarios comparaient un offline execute a un live vide).

        ⚠ Le critere n'est PAS `mutated` : un cast qui ne fait que POSER DES EFFETS (MomentShackle
        sur un porteur a PV pleins -> heal 0) execute tout son arbre et rend pourtant
        `mutated = False`. Le discriminant MESURE est le compte d'evenements -- un cast REFUSE en
        rend exactement **2** (le groupe `User_UseAbility` ouvert puis referme aussitot, cf.
        case-111), un cast execute en rend davantage."""
        r = self.act({"kind": "ability", "casterId": caster, "targetId": target,
                      "abilityType": ability})
        inner = (r.get("actions") or [{}])[0]
        assert inner.get("ok") and int(inner.get("eventCount") or 0) > 2, (
            "cast live refuse (2 evenements = groupe ouvert/referme) : %s"
            % {k: inner.get(k) for k in ("ok", "error", "eventCount", "currentPlayer")})
        return r

    def my_turn(self, team_player):
        """Rend la main a `team_player` (le natif refuse un cast hors du tour de son proprietaire)."""
        for _ in range(6):
            if self.dv().get("currentPlayer") == team_player:
                return True
            self.act({"kind": "endturn"}, 40)
        return False

    # -- offline
    def state(self):
        st = load_state(self.dv(), self.ob(),
                        self.rpc("combatSnapshot", {"runnerId": self.rid}, 60), board=self.board)
        return _seed(st, self.rpc("dumpRng", {"runnerId": self.rid}, 30))

    # -- geometrie DERIVEE du board (aucune tuile en dur)
    def geometry(self):
        """(T0, T1, A, B) : `T1` a >= 3 voisins marchables ; `T0` est un voisin de `T1` ; `A` est
        voisin de T0 **ET** de T1 (« deja adjacent avant le pas ») ; `B` est voisin de T1 mais PAS
        de T0 (« nouvellement adjacent »). C'est cette paire A/B qui separe `IsCharging` de
        `HasMoved`."""
        b = self.board

        def nb(coord):
            """Voisinage retenu = l'INTERSECTION du graphe natif (`board.neighbours`, la verite du
            moteur pour ce qui est « adjacent ») et de la distance hex (ce que lit le selecteur
            `AdjacentEnemies` du port). Les deux divergent sur certaines tuiles de ce board ; batir
            la geometrie sur l'un seul fait mesurer un desaccord de HARNAIS et non le port (vecu :
            la cible B, `hexgeo`-adjacente mais absente du graphe natif, n'etait frappee QU'offline)."""
            t = b.id_at(coord[0], coord[1])
            if t is None:
                return set()
            out = set()
            for n in (b.neighbours(t) or ()):
                c = b.coord(n)
                if b.walkable(n) and hexgeo.distance(c, coord) == 1:
                    out.add(c)
            return out

        walk = [b.coord(t) for t in sorted(b.by_id) if b.walkable(t)]
        # On exige une tuile CENTRALE (6 voisins) : un coin/bord n'a que 2-3 voisins, ce qui
        # sous-exerce silencieusement toute mecanique d'adjacence (memoire « choisir le board »).
        for t1 in walk:
            nb1 = nb(t1)
            if len(nb1) < 6:
                continue
            for t0 in sorted(nb1):
                nb0 = nb(t0)
                common = sorted(c for c in nb1 if c in nb0 and c != t0)
                only1 = sorted(c for c in nb1 if c not in nb0 and c != t0)
                if common and only1:
                    return t0, t1, common[0], only1[0]
        pytest.skip("board sans geometrie T0/T1/A/B (voisinage insuffisant)")

    def park_far(self, uid, ref, occupied=()):
        """Range une unite LOIN du theatre (dist > 5) sur une tuile marchable ET LIBRE."""
        b = self.board
        busy = {_pos(u) for u in _units(self.dv()) if u.get("id") != uid} | set(occupied)
        far = [b.coord(t) for t in sorted(b.by_id)
               if b.walkable(t) and hexgeo.distance(b.coord(t), ref) > 5
               and b.coord(t) not in busy]
        assert far, "aucune tuile de parking libre"
        self.place(uid, far[len(far) // 2])


@pytest.fixture
def arena(rpc, build_runner):
    """Runner ISOLE frais (Titus + Trajann vs 2 ennemis sans riposte), auto-dispose en fin de test.
    UN runner PAR test : chaque ability du lot est a usage unique dans la bataille."""
    rid = build_runner("4242", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    a = Arena(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    dv = a.dv()
    if _by_vis(dv, TITUS) is None or _by_vis(dv, TRAJANN) is None:
        pytest.skip("Titus/Trajann absents du build")
    return a


def _setup_tp(a, titus_final_is_a_step: bool):
    """Monte la geometrie de reference et renvoie `(titus, foeA, foeB, T1)`.

    `titus_final_is_a_step=False` : Titus est POSE directement sur T1 pendant que les ennemis sont
    encore au spawn -> aucune unite ne devient adjacente pendant SON pas -> `ChargedUnitIds` VIDE.
    `True` : Titus est pose sur T0, les ennemis prennent A et B, PUIS Titus fait le pas T0 -> T1 --
    seul `B` devient nouvellement adjacent (`A` l'etait deja depuis T0)."""
    T0, T1, A, B = a.geometry()
    dv = a.dv()
    titus, traj = _by_vis(dv, TITUS), _by_vis(dv, TRAJANN)
    foes = [u for u in _units(dv) if u.get("team") != titus.get("team")]
    assert len(foes) >= 2, "2 ennemis requis"
    # ORDRE OBLIGATOIRE : Trajann DEGAGE d'abord (il occupe une tuile de spawn voisine de celle de
    # Titus -- le laisser en place fait refuser silencieusement les poses suivantes), puis Titus,
    # puis les ennemis. Titus AVANT les ennemis : c'est ce qui garantit que son pas de mise en
    # place ne charge personne (les ennemis sont encore a leur spawn, loin).
    a.park_far(traj["id"], T1, occupied={T0, T1, A, B})
    a.place(titus["id"], T0 if titus_final_is_a_step else T1)
    a.place(foes[0]["id"], A)
    a.place(foes[1]["id"], B)
    return titus["id"], foes[0]["id"], foes[1]["id"], T1


def _confront_cast(a, caster, target, ability, pre_move=None):
    """Joue le cast des DEUX cotes et renvoie `(diag_offline, deltas_live, deltas_offline)`.

    Le `pre_move` eventuel est joue **des deux cotes** (live `applyAction`, offline
    `MoveUnitMessage` a travers un `Runner` AVEC ses handlers) : c'est CE pas qui doit alimenter
    `ChargedUnitIds` offline. Declarer la liste a la main court-circuiterait le morceau de port
    qu'on veut confronter. Le PRNG est RE-seede APRES le pas, pour que seul le CAST soit compare."""
    # RENDRE LA MAIN AU CASTER D'ABORD. Les poses de montage consomment des activations et font
    # BASCULER le tour ; le natif refuse alors le cast (`mutated=False`, `ok=True` -- silencieux).
    # Ce `endturn` doit precederle `pre_move` : sinon `FinishUnitTurnOperation` VIDERAIT
    # `ChargedUnitIds` juste apres l'avoir rempli, et la branche CHARGE ne serait jamais atteinte.
    owner = next((u.get("owner") for u in _units(a.dv()) if u.get("id") == caster), None)
    assert a.my_turn(owner), "impossible de rendre la main au caster"
    st = a.state()
    ids = sorted(_hp_live(a.ob()))
    before = _hp_live(a.ob())
    if pre_move is not None:
        Runner(st).install_default_handlers().apply(MoveUnitMessage(caster, pre_move))
        a.place(caster, pre_move)
        _seed(st, a.rpc("dumpRng", {"runnerId": a.rid}, 30))
    klass = TacticalPrecisionAbility if ability == TP else MomentShackleAbility
    diag = klass().execute_behaviour(st, caster, target)
    off_after = _hp_off(st, ids)
    assert a.cast(caster, target, ability).get("ok"), "cast live refuse"
    live_after = _hp_live(a.ob())
    return (diag,
            {u: live_after.get(u, 0) - before[u] for u in ids},
            {u: off_after.get(u, 0) - before[u] for u in ids})


# --------------------------------------------------------------------------- TacticalPrecision

def test_tp_sans_charge_frappe_tous_les_adjacents_live(arena):
    """CAS 1 -- Titus n'a PAS bouge : branche `else` = 3x Chain sur **tous** les AdjacentEnemies du
    CASTER (pas seulement la cible du message). Live == offline, PAR CIBLE."""
    titus, foe_a, foe_b, _ = _setup_tp(arena, titus_final_is_a_step=False)
    diag, live_d, off_d = _confront_cast(arena, titus, foe_a, TP)
    assert diag["charging"] is False, diag
    assert live_d == off_d, (live_d, off_d)
    assert live_d[foe_a] < 0 and live_d[foe_b] < 0, ("les DEUX adjacents doivent morfler", live_d)
    assert live_d[titus] == 0


def test_tp_en_charge_frappe_la_seule_cible_live(arena):
    """CAS 2 -- MEME geometrie, mais Titus arrive AU CONTACT par son pas : branche `then` =
    1x Bolter FORCE-CRIT sur la SEULE cible. Le second adjacent est intact -- c'est ce qui rend le
    couple de cas discriminant (meme etat, observables opposes)."""
    titus, foe_a, foe_b, T1 = _setup_tp(arena, titus_final_is_a_step=True)
    diag, live_d, off_d = _confront_cast(arena, titus, foe_b, TP, pre_move=T1)
    assert diag["charging"] is True, diag
    assert live_d == off_d, (live_d, off_d)
    assert live_d[foe_b] < 0, live_d
    assert live_d[foe_a] == 0, ("branche CHARGE = mono-cible", live_d)


def test_tp_charge_nest_pas_has_moved_live(arena):
    """CAS 3 -- LE test du socle. Titus BOUGE (donc `HasMoved` est VRAI), mais la cible etait
    **deja adjacente avant le pas** -> elle n'entre pas dans `ChargedUnitIds` -> `IsCharging` est
    FAUX et c'est la branche NON-CHARGE qui tourne (3x Chain sur tous les adjacents).

    Un port qui modeliserait le pivot par `HasMoved` prendrait ici la branche CHARGE : 1 coup sur
    une seule cible au lieu de 3 coups sur deux cibles. Les deux observables sont incompatibles."""
    titus, foe_a, foe_b, T1 = _setup_tp(arena, titus_final_is_a_step=True)
    diag, live_d, off_d = _confront_cast(arena, titus, foe_a, TP, pre_move=T1)
    assert diag["charging"] is False, ("cible deja adjacente AVANT le pas -> pas de charge", diag)
    assert live_d == off_d, (live_d, off_d)
    assert live_d[foe_a] < 0 and live_d[foe_b] < 0, ("branche NON-CHARGE = tous adjacents", live_d)


def test_force_crit_change_le_degat_ab_offline(arena):
    """A/B du FLAG lui-meme, a etat et PRNG IDENTIQUES : `force_crit=True` vs `False`.

    Sans ce test, rien ne dit que le flag PORTE quelque chose -- Titus a `CritChance = 0`, donc la
    voie normale ne peut JAMAIS crit : un port qui ignorerait l'octet +5 rendrait tranquillement la
    valeur non-crit, et l'egalite live/offline des cas 1-3 ne le verrait pas (le cas 1 ne passe pas
    par cette branche). On compare donc les DEUX valeurs sur le meme tirage."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.abilities.base import ability_attack_params
    titus, foe_a, _foe_b, T1 = _setup_tp(arena, titus_final_is_a_step=True)
    arena.place(titus, T1)
    rng0 = arena.rpc("dumpRng", {"runnerId": arena.rid}, 30)
    st0 = arena.state()
    sc = st0.get_entity(titus).get_component(StatsComponent)
    assert sc.ctx.stat(StatType.CRIT_CHANCE) == 0, "porteur a CritChance != 0 : A/B non concluant"
    bmin, bmax, pierce, hits = ability_attack_params(st0, titus, "TacticalPrecision", "Bolter")
    from engine.entities.effects.magnitude import ability_var
    crit_amount = int(ability_var("TacticalPrecision", "extraCritDmg",
                                  sc.ctx.active_ability_level,
                                  multiplier_pct=sc.ctx.ability_variables_multiplier) or 0)
    assert crit_amount > 0

    totals = {}
    for flag in (True, False):
        st = _seed(arena.state(), rng0)
        # le couple ChangeStat de l'arbre est REJOUE ici (c'est lui qui alimente le bonus de crit) :
        # sans lui `CriticalDamage` vaut 0 et le crit n'ajouterait rien -- l'A/B serait muet.
        st.get_entity(titus).get_component(StatsComponent).ctx.stats.change_stat(
            int(StatType.CRIT_DAMAGE), ("tp_ab", titus), crit_amount)
        r = AttackDamageOperation.execute_ability_attack(
            st, titus, foe_a, bmin, bmax, pierce, hits, damage_profile="Bolter", is_melee=True,
            ability_type=TP, force_crit=flag)
        totals[flag] = (r["total"], r["crits"])
    assert totals[True][1] == [True] and totals[False][1] == [False], totals
    assert totals[True][0] > totals[False][0], (
        "l'octet +5 doit CHANGER le degat (crit acquis + extraCritDmg) : %s" % (totals,))


# --------------------------------------------------------------------------- MomentShackle

def _cast_ms(a, traj):
    return _confront_cast(a, traj, traj, MS)


def test_moment_shackle_pv_pleins_et_stat_mods_live(arena):
    """CAS 1 -- Trajann a PV PLEINS : le heal est PLAFONNE a 0 (aucune garde `Healable` dans
    l'arbre natif -- c'est le plafond `hp_max` de `HealUnitOperation` qui tranche), et les DEUX
    `DynamicStatModifierEffect` sont poses. Ce sont EUX l'observable : `statModSources` doit rendre
    exactement `blockChance[level]` et `blockDmg[level] x multiplier` du CASTER."""
    dv = arena.dv()
    traj = _by_vis(dv, TRAJANN)
    diag, live_d, off_d = _cast_ms(arena, traj["id"])
    assert live_d == off_d, (live_d, off_d)
    assert live_d[traj["id"]] == 0, ("PV pleins -> heal plafonne a 0", live_d)
    assert sorted(p["effect"] for p in diag["posed"]) == [1391, 1392, 1393], diag

    from engine.entities.effects.magnitude import ability_var
    st = arena.state()
    ctx = st.get_entity(traj["id"]).get_component(StatsComponent).ctx
    want = {"blockChance": int(ability_var("MomentShackle", "blockChance", ctx.active_ability_level,
                                           multiplier_pct=ctx.ability_variables_multiplier)),
            "blockDamage": int(ability_var("MomentShackle", "blockDmg", ctx.active_ability_level,
                                           multiplier_pct=ctx.ability_variables_multiplier))}
    sm = arena.rpc("statModSources", {"runnerId": arena.rid}, 40)
    live_mods = {}
    for u in ((sm or {}).get("units") or []):
        if int(u.get("entityId") or -1) == int(traj["id"]):
            live_mods = {k: v.get("total") for k, v in (u.get("mods") or {}).items()}
    assert live_mods.get("blockChance") == want["blockChance"], (live_mods, want)
    assert live_mods.get("blockDamage") == want["blockDamage"], (live_mods, want)


def test_moment_shackle_blesse_soigne_live(arena):
    """CAS 2 -- MEME cast sur un Trajann BLESSE : le heal vaut cette fois `min(manquant,
    hpToHeal[level] x multiplier)`, un nombre DIFFERENT de zero -> les deux cas ne peuvent pas
    etre satisfaits par un meme scalaire fitte. On fait encaisser Trajann par des tours d'IA
    adverse (`aiturn`), puis on confronte le heal live au heal offline."""
    dv = arena.dv()
    traj = _by_vis(dv, TRAJANN)
    tid = traj["id"]
    from engine.runner.components import HealthComponent
    hp_max = arena.state().get_entity(tid).get_component(HealthComponent).hp_max
    # On AMENE Trajann au contact des deux ennemis puis on laisse l'IA adverse jouer : c'est le
    # seul levier qui fait BAISSER des PV live sans toucher aux maximums (`--hp-player`, lui, force
    # `Health` ET `RemainingHealth` -> l'unite reste a PV pleins et le heal resterait plafonne a 0).
    T0, T1, A, B = arena.geometry()
    titus = _by_vis(arena.dv(), TITUS)
    arena.park_far(titus["id"], T1, occupied={T0, T1, A, B})
    arena.place(tid, T1)
    foes = [u for u in _units(arena.dv()) if u.get("team") != traj.get("team")]
    for f, c in zip(foes, (A, B)):
        arena.place(f["id"], c)
    for _ in range(4):
        if _hp_live(arena.ob()).get(tid, 0) < hp_max:
            break
        arena.act({"kind": "endturn"}, 40)
        arena.rpc("aiPlayByUnit", {"runnerId": arena.rid, "maxTurns": 1,
                                   "maxActivations": 9999}, 300)
        arena.act({"kind": "endturn"}, 40)
    hp_now = _hp_live(arena.ob()).get(tid, 0)
    st = arena.state()
    hc = st.get_entity(tid).get_component(HealthComponent)
    if hc is None or not hc.hp_max or hp_now >= hc.hp_max:
        pytest.skip("Trajann jamais blesse par l'IA sur ce build -- cas non monte")
    diag, live_d, off_d = _cast_ms(arena, tid)
    assert live_d == off_d, (live_d, off_d)
    assert live_d[tid] > 0, ("Trajann blesse -> heal STRICTEMENT positif", live_d)
    assert live_d[tid] == min(hc.hp_max - hp_now, diag["heal_amount"]), (live_d, diag)
