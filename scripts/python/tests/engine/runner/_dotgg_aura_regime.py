"""Helper REUTILISABLE du REGIME D'AURA `DefenderOfTheGreaterGood` (#372) -- confronte le nombre de
COUPS live vs offline pour un BENEFICIAIRE place a une distance CHOISIE du porteur.

Pendant d'`_charge_regime.py` : ici on monte les regimes que le SELECTEUR natif
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`
SEPARE, et qu'un port sans gate de distance/faction CONFONDRAIT :

    sel = AdjacentFriends(Owner, ownerTiles, includeSelf = 1) - Owner            # range 1, TOUTE faction
    sel = Unique( sel + UnitsFromFaction(SurroundingFriends(Owner, 2), 9 = Tau) ) # range 2, T'au SEULEMENT
    sel = UnitsWithRangedWeaponsExcludingDamageProfile( sel, 0xd = Psychic )

  * `ADJACENT`      -- beneficiaire NON-T'au a d=1 du porteur  -> DANS le selecteur  -> +extraHit.
  * `RING2_NON_TAU` -- LE MEME beneficiaire a d=2               -> HORS du selecteur -> rien.
                       C'est LE regime DISCRIMINANT du tier de distance : meme unite, meme arme,
                       meme cible, seule la distance au porteur change.
  * `RING2_TAU`     -- beneficiaire T'AU a d=2                  -> DANS le selecteur -> +extraHit.
                       Discrimine le tier de FACTION contre `RING2_NON_TAU`.
  * `FAR`           -- beneficiaire a d=4                       -> TEMOIN (hors de toute portee).

POURQUOI LE NOMBRE DE COUPS, ET PAS UN SCALAIRE : l'observable est DISCRETE (`len(per_hit)`). Un
ecart d'un coup ne peut etre ni absorbe ni compense par un regime d'armure, de percage ou de crit.

LE REGIME DE CHANCE EST PILOTE, PAS SUBI. Le bonus est gate par
`Maybe( Min(Direct(100), Multiply(ConfigConst(0x2a = chance = 25), UnitTurnsStarted(porteur))) )`.
Le harnais fait donc tourner des tours a VIDE jusqu'a `turnsStarted(porteur) >= 4`, ou la chance
atteint 100 : les DEUX faces y concordent sans aleatoire
(`IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` : `99 < chance` sans PRNG, `NextBool(100)`
avec). En-dessous, le coup est un TIRAGE et la mesure ne conclurait rien.

PROTOCOLE (chaque marche a deja coute une mesure fausse) :

  1. PLACER d'abord, `reach_my_turn(force_cycle=True)` ENSUITE -- un `applyAction move` consomme
     l'activation du beneficiaire ; l'attaque suivante est alors refusee et rend `per_hit` VIDE
     (mesure #372 : `n=0` sur un montage sans cycle force).
  2. SNAPSHOT juste AVANT l'attaque, `dumpRng` APRES le snapshot : la face COMBAT du `Maybe` TIRE
     (`DisallowablePseudoRNG$$NextBool` consomme un genrand), donc les deux cotes doivent partir du
     MEME etat de PRNG.
  3. Le porteur est place LOIN de la cible (d >= 3) : on ne veut ni qu'il tire, ni qu'il encaisse.
  4. `applyAction {kind:"move"}` rend `ok=True` MEME quand le pas est refuse -> on RELIT la position.

Usage (fixture nommee `dotgg_aura_regime`, factory de portee session) :

    from _dotgg_aura_regime import dotgg_aura_regime, ADJACENT      # noqa: F401  (fixture)

    def test_x(dotgg_aura_regime):
        h = dotgg_aura_regime(benef="darkaHellblaster")
        rec = h.run(ADJACENT)
        off = h.replay_offline(rec)

ASCII only (console cp1252).
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

CARRIER = "tauShadowsun"        # HERO du pool, porteur du passif DefenderOfTheGreaterGood

ADJACENT = "ADJACENT"           # d=1, toute faction        -> DANS le selecteur
RING2_NON_TAU = "RING2_NON_TAU"  # d=2, faction != Tau       -> HORS du selecteur (discriminant)
RING2_TAU = "RING2_TAU"         # d=2, faction Tau          -> DANS le selecteur
FAR = "FAR"                     # d=4                       -> TEMOIN

# distance porteur <-> beneficiaire imposee par chaque regime
REGIME_DIST = {ADJACENT: 1, RING2_NON_TAU: 2, RING2_TAU: 2, FAR: 4}
# chance = min(100, 25 x turnsStarted) -> 4 tours suffisent a saturer le `Maybe`
TURNS_FOR_CERTAINTY = 4


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _seed_rng(dump):
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


class DotggAuraHarness:
    """Une bataille isolee ou l'on impose la position du beneficiaire par rapport au porteur.

    Le harnais ne fait AUCUN assert : il rend le nombre de coups live et le rejeu offline, le test
    appelant tranche."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board
        self.my_player = None

    # ------------------------------------------------------------------ lecture d'etat live

    def dview(self):
        return self.rpc("decisionView",
                        {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)

    def alive(self, dv=None):
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, visual_id, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == visual_id), None)

    def normal_attack_type(self, unit_id, dv=None):
        """L'attaque normale est un `ActiveAbilityType` PAR UNITE (`kind == 'normal'`)."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") == unit_id:
                for a in (u.get("abilities") or []):
                    if a.get("kind") == "normal":
                        return a.get("id")
        return None

    def turns_started(self, unit_id, snap=None):
        snap = snap if snap is not None else self.rpc("combatSnapshot", {"runnerId": self.rid}, 60)
        for u in (snap.get("units") or []):
            if u.get("entityId") == unit_id:
                return (u.get("stats") or {}).get("turnsStarted")
        return None

    # ------------------------------------------------------------------ pilotage

    def place(self, unit_id, coord):
        """Pose `unit_id` sur `coord` (`applyAction` ne verifie NI propriete NI portee).
        RELIT la position -> True SSI le pas a reellement eu lieu."""
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": int(unit_id),
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
        u = next((x for x in self.alive() if x.get("id") == unit_id), None)
        return u is not None and _upos(u) == (int(coord[0]), int(coord[1]))

    def reach_my_turn(self, max_end_turns=12, force_cycle=True):
        """Enchaine des `endturn` jusqu'a mon tour. `force_cycle=True` passe par UN CYCLE COMPLET
        meme si c'est deja mon tour : sans lui, l'activation consommee par les `place()` du montage
        fait REFUSER l'attaque et le harnais rend `per_hit` VIDE (mesure #372)."""
        dv = self.dview()
        if self.my_player is None:
            mine = self.alive(dv)
            self.my_player = mine[0].get("owner") if mine else None
        if force_cycle and dv.get("currentPlayer") == self.my_player:
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
            dv = self.dview()
        for _ in range(max_end_turns):
            if dv.get("currentPlayer") == self.my_player:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
            dv = self.dview()
        return dv if dv.get("currentPlayer") == self.my_player else None

    def warm_turns(self, carrier_id, target=TURNS_FOR_CERTAINTY, max_cycles=14):
        """Fait tourner des tours A VIDE jusqu'a `turnsStarted(porteur) >= target`.

        C'est ce qui porte `chance = Min(Direct(100), Multiply(ConfigConst(0x2a = 25),
        UnitTurnsStarted(porteur)))` a 100, donc le seul regime ou le `Maybe` du trigger est
        DETERMINISTE des deux cotes."""
        for _ in range(max_cycles):
            ts = self.turns_started(carrier_id)
            if ts is not None and ts >= target:
                return ts
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
        return self.turns_started(carrier_id)

    def free_coords(self):
        """Coordonnees MARCHABLES du board, ordre deterministe (id de tuile croissant)."""
        return [self.board.coord(t) for t in sorted(self.board.by_id) if self.board.walkable(t)]

    def snapshot(self):
        return {
            "dv": self.dview(),
            "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 40),
            "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 60),
            "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 30),
        }

    # ------------------------------------------------------------------ montage du regime

    def arrange(self, benef_visual, regime):
        """Impose la geometrie du regime et rend `{carrier, benef, target, anchor, ...}` ou None.

        On DEPLACE les unites -- jamais « bloque par la geometrie de spawn ». L'ennemi est ancre sur
        une tuile a 6 voisins marchables ; le porteur est pose a d>=3 de lui (il ne tire ni
        n'encaisse) ; le beneficiaire est pose a `REGIME_DIST[regime]` du porteur ET a portee de tir
        de l'ennemi."""
        dist = REGIME_DIST[regime]
        dv = self.dview()
        car = self.by_visual(CARRIER, dv)
        ben = self.by_visual(benef_visual, dv)
        if car is None or ben is None:
            return None
        self.my_player = car.get("owner")
        ens = [u for u in self.alive(dv) if u.get("owner") != self.my_player]
        if not ens:
            return None
        tgt = ens[0]
        coords = self.free_coords()
        anchors = [c for c in coords
                   if len([n for n in coords if hexgeo.distance(c, n) == 1]) == 6]
        others = [u for u in self.alive(dv)
                  if u["id"] not in (car["id"], ben["id"], tgt["id"])]
        for anc in anchors:
            for cpos in [c for c in coords if hexgeo.distance(c, anc) >= 3 and c != anc]:
                bs = [c for c in coords
                      if hexgeo.distance(c, cpos) == dist and c not in (anc, cpos)
                      and 2 <= hexgeo.distance(c, anc) <= 3]
                if not bs:
                    continue
                bpos = bs[0]
                used = {anc, cpos, bpos}
                for o in others:                       # ecarter tout le reste
                    far = [c for c in coords if c not in used and hexgeo.distance(c, anc) >= 5]
                    if far and self.place(o["id"], far[0]):
                        used.add(far[0])
                if not (self.place(tgt["id"], anc) and self.place(car["id"], cpos)
                        and self.place(ben["id"], bpos)):
                    continue
                return {"carrier": car["id"], "benef": ben["id"], "target": tgt["id"],
                        "anchor": anc, "carrier_pos": cpos, "benef_pos": bpos, "regime": regime}
        return None

    def run(self, benef_visual, regime):
        """Monte le regime, sature la chance, SNAPSHOTe puis joue l'ATTAQUE NORMALE du beneficiaire.

        Rend `{...arrange, turns_started, snapshot, live_per_hit, ability_type}` ou None si la
        geometrie n'a pas pu etre obtenue."""
        plan = self.arrange(benef_visual, regime)
        if plan is None:
            return None
        if self.reach_my_turn() is None:
            return None
        plan["turns_started"] = self.warm_turns(plan["carrier"])
        if self.reach_my_turn(force_cycle=False) is None:
            return None
        dv = self.dview()
        pos = {u["id"]: _upos(u) for u in self.alive(dv)}
        # GARDE DE REGIME : la geometrie doit dire ce que le regime PROMET, sinon le verdict porte
        # sur autre chose que ce que le test croit mesurer.
        if (pos.get(plan["benef"]) != plan["benef_pos"]
                or pos.get(plan["carrier"]) != plan["carrier_pos"]
                or pos.get(plan["target"]) != plan["anchor"]):
            return None
        if hexgeo.distance(plan["benef_pos"], plan["carrier_pos"]) != REGIME_DIST[regime]:
            return None
        plan["ability_type"] = self.normal_attack_type(plan["benef"], dv)
        if plan["ability_type"] is None:
            return None
        plan["snapshot"] = self.snapshot()
        # Face PREDICTION capturee AVANT l'attaque (elle ne mute rien) : les DEUX consommateurs de
        # la formule de coups sont ainsi confrontes sur le MEME etat.
        plan["predict_rows"] = self.predict_rows(plan)
        res = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": plan["benef"], "targetId": plan["target"],
            "abilityType": int(plan["ability_type"])}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        hits = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if ("Amount" in td and td.get("Attacker_Id") == plan["benef"]
                    and td.get("Target_Id") == plan["target"]):
                hits.append(int(td["Amount"]))
        plan["live_ok"] = bool(_ok(res) and a0.get("ok"))
        plan["live_per_hit"] = hits
        return plan

    # ------------------------------------------------------------------ rejeu offline

    def offline_state(self, rec):
        """Reconstruit un `State` OFFLINE depuis le snapshot pris juste avant l'attaque, MT cale sur
        le meme dump : la face COMBAT du `Maybe` TIRE, les deux cotes doivent partir du meme flux."""
        s = rec["snapshot"]
        st = load_state(s["dv"], s["ob"], s["snap"], board=self.board)
        dump = s["rng"]
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = _seed_rng(dump)
        return st

    def replay_offline(self, rec):
        """Rejoue l'ATTAQUE NORMALE offline et rend
        `{per_hit, weapon_per_hit, extra_per_hit, state, carrier_effects}`.

        ⚠ `per_hit` CONCATENE les coups d'ARME **et** les coups des groupes du canal #179
        (`damage_handler.last["additional_hits"]["per_hit"]`), dans cet ordre. C'est ce qui le rend
        COMPARABLE au compte LIVE, qui ramasse TOUS les evenements de degat de l'attaque.
        Sans cette concatenation, tout beneficiaire portant un descripteur `EffectAdditionalHits`
        (ex. `tauCrisis` / `CyclicIonBlaster_AdditionalHits`, `nrOfHits = 3`) fait rendre au harnais
        un delta CONSTANT -- mesure #372 : `live n=10` contre `offline n=7`, les 7 premiers coups
        BIT-EXACTS. Ce rouge-la accuse le MONTAGE, pas le port ; il a ete pris pour un manque de
        `+extraHit` avant d'etre localise."""
        st = self.offline_state(rec)
        effs = [getattr(e, "name", None)
                for e in (st.effects.by_unit.get(rec["carrier"]) or [])]
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=rec["benef"], target_id=rec["target"]))
        last = runner.damage_handler.last or {}
        weapon = list(last.get("per_hit") or [])
        extra = list(((last.get("additional_hits") or {}).get("per_hit")) or [])
        return {"per_hit": weapon + extra, "weapon_per_hit": weapon, "extra_per_hit": extra,
                "state": st, "carrier_effects": effs}

    # ------------------------------------------------ face PREDICTION (l'autre consommateur)

    def predict_rows(self, rec):
        """Confronte la face PREDICTION -- l'ORACLE natif per-tuile (`decisionView.attackPlans[].
        evals[].ranked`, produit par `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`)
        contre `playbook.prediction.make_normal_attack_predictions` du port, POUR LE BENEFICIAIRE.

        La formule de coups est PARTAGEE par les deux faces (le natif ne la duplique pas) : cette
        confrontation ferme la face que le rejeu de combat ne touche pas. Elle a lieu APRES le
        rechauffement des tours, donc dans le regime `chance = 100` ou `Maybe` est deterministe des
        DEUX cotes (`MaybeTrigger$$ShouldTrigger` sans PRNG = `99 < chance`).

        Rend `[{tile, d_carrier, oracle: (min,max), offline: (min,max)}]` -- l'appelant tranche."""
        from engine.playbook import scene as SC
        from engine.playbook import prediction
        from engine.playbook.scene import Scene
        dec = self.rpc("decisionView",
                       {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)
        predictor = SC.build_predictor(self.rpc, self.rid)
        if predictor is None:
            return None
        sctx = SC.step_context(predictor, dec)
        scene = Scene.from_predictor_sctx(predictor, sctx, None)
        ben, tgt = rec["benef"], rec["target"]
        if ben not in (predictor.get("ctx_by_id") or {}):
            return None
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == ben
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        rows = []
        for ap in (dec.get("attackPlans") or []):
            if ap.get("unitId") != ben:
                continue
            for ev in (ap.get("evals") or []):
                if ev.get("targetId") != tgt:
                    continue
                if norm_ids and ev.get("abilityId") not in norm_ids:
                    continue
                for rk in (ev.get("ranked") or []):
                    if rk.get("dmgMax") is None or rk.get("col") is None:
                        continue
                    tile = (rk["col"], rk["row"])
                    off = prediction.make_normal_attack_predictions(scene, ben, tgt, tile)
                    res = off.prediction.accurate_health_damage
                    rows.append({"tile": tile,
                                 "d_carrier": hexgeo.distance(tile, rec["carrier_pos"]),
                                 "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                                 "offline": (res.min, res.max)})
        return rows

    def dispose(self):
        self.rpc("disposeRunner", {"runnerId": self.rid}, 20)


@pytest.fixture(scope="session")
def dotgg_aura_regime(rpc, build_runner):
    """FABRIQUE de `DotggAuraHarness` -- fixture NOMMEE, reutilisable.

    `make(benef=..., seed=..., board=..., a_units=...)`. Le roster porte TOUJOURS `tauShadowsun`
    (le porteur) ; `benef` doit etre un allie a arme RANGED. Les PV sont gonfles pour que rien ne
    meure pendant le rechauffement des tours (le montage a besoin de >= 4 tours)."""
    def make(benef, seed="777", board="MC1_67", a_units="orksNob", extra=None):
        p_units = "%s,%s" % (CARRIER, benef)
        args = ["--p-units", p_units, "--a-units", a_units,
                "--hp-target", "300000", "--hp-player", "300000", "--no-ai", *(extra or [])]
        rid = build_runner(seed, extra=args, board=board)["rid"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.fail("boardGraph indispo -- montage NON INSTALLE", pytrace=False)
        h = DotggAuraHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        if not _ok(h.dview()):
            pytest.fail("decisionView KO -- montage NON INSTALLE", pytrace=False)
        return h
    return make
