"""Helper REUTILISABLE du REGIME DE CHARGE -- confronte `BattleQuery$$IsCharging` live vs offline.

Pendant d'`_ability_cast_replay.py` (cast d'ability) et d'`_pierce_floor_regime.py` (regime de
percage) : ici on monte les DEUX regimes que le predicat natif
`IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` SEPARE, et que le proxy
« l'unite a-t-elle bouge » (`UnitFlag.Moved`) CONFOND :

  * `CHARGE`        -- le caster part d'une tuile NON adjacente a la cible et arrive AU CONTACT.
                       `MoveUnitOperation$$UpdateCharging` ajoute la cible aux `ChargedUnitIds`
                       -> `IsCharging` VRAI.
  * `STEP_ADJACENT` -- le caster part d'une tuile DEJA adjacente a la cible et se deplace vers une
                       AUTRE tuile encore adjacente. `UpdateCharging` n'ajoute QUE les unites
                       NOUVELLEMENT adjacentes : la cible ne l'est pas -> `IsCharging` FAUX, alors
                       que le flag `Moved` est VRAI. C'est LE cas discriminant (case-231 §6 sc. 3).

Le harnais ne fait AUCUN assert : il rend les degats per-coup live et le rejeu offline, le test
appelant tranche.

PROTOCOLE (chaque marche a deja coute une mesure fausse, cf. les fiches citees) :

  1. PLACER d'abord, `reach_my_turn()` ENSUITE -- un `applyAction move` consomme une activation et
     peut FAIRE BASCULER le joueur courant ; le cast suivant est alors refuse EN SILENCE (`ok=True`,
     aucun `mutated`, 2 evenements, zero degat -- signature #111). Repasser par `reach_my_turn()`
     donne au caster un tour NEUF, flags purges (`StartTurnOperation$$ResetUnit`) : il n'a donc PAS
     bouge, et sa liste `ChargedUnitIds` a ete videe par `FinishUnitTurnOperation$$Execute`.
  2. SNAPSHOT **avant** le pas -- c'est le pas lui-meme qui remplit `ChargedUnitIds`, donc l'offline
     doit le REJOUER (`MoveUnitMessage`), jamais declarer la liste a la main : declarer
     court-circuiterait justement le morceau de port qu'on confronte.
  3. `Runner(...).install_default_handlers()` est INDISPENSABLE avant `apply` -- un `Runner` nu n'a
     aucun visiteur, `apply` ne fait rien et `charged_unit_ids` reste vide (le port paraitrait faux
     alors que le move n'a pas eu lieu).
  4. RE-SEED du MT **apres** le pas live : le flux a pu bouger (cascade after-move) ; les deux cotes
     doivent partir du MEME etat de PRNG pour que seule l'ATTAQUE soit comparee.
  5. `applyAction {kind:"move"}` rend `ok=True` MEME quand le pas est refuse (tuile occupee /
     non marchable) -> on RELIT la position apres chaque pose (`place`/`step` rendent un booleen).

Usage (fixture nommee `charge_regime`, factory de portee session) :

    from _charge_regime import charge_regime          # noqa: F401  (fixture)

    def test_x(charge_regime):
        h = charge_regime(p_units="astraBullgryn", a_units="necroOverlord,necroWarden")
        rec = h.run(regime="STEP_ADJACENT", caster_visual="astraBullgryn")
        off = h.replay_offline(rec)

ASCII only (console cp1252).
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.messages import AttackUnitMessage, MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

CHARGE = "CHARGE"                    # part de loin, arrive au contact -> IsCharging VRAI
STEP_ADJACENT = "STEP_ADJACENT"      # part deja au contact, se decale -> IsCharging FAUX
NO_STEP = "NO_STEP"                  # n'a pas bouge du tour -> IsCharging FAUX (controle)


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


class ChargeRegimeHarness:
    """Une bataille isolee ou l'on impose le regime de charge du caster, action par action.

    Attributs : `rid` (runnerId), `board` (`Board`, adjacence `native_sym`), `my_player`."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board
        self.my_player = None
        # TRACE du montage : chaque `place()` REEL est un `MoveUnitOperation` natif, donc un appel a
        # `UpdateCharging`. Sans cette trace, une charge posee PAR LE MONTAGE se lit comme un ecart
        # de port (mesure case-ischarging-hits). Format : (unit_id, from_pos, to_pos, moved).
        self.trace: list = []
        self.endturns = 0

    # ------------------------------------------------------------------ lecture d'etat live

    def dview(self):
        return self.rpc("decisionView",
                        {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)

    def alive(self, dv=None):
        """Unites VIVANTES (le `decisionView` GARDE les cadavres)."""
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, visual_id, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == visual_id), None)

    def enemies_of(self, player, dv=None):
        return [u for u in self.alive(dv) if u.get("owner") != player]

    def normal_attack_type(self, unit_id, dv=None):
        """L'attaque normale est un `ActiveAbilityType` PAR UNITE (`kind == 'normal'` du
        `decisionView`), jamais l'id generique 17 -- cf. `NormalAttackType@0x28`."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") == unit_id:
                for a in (u.get("abilities") or []):
                    if a.get("kind") == "normal":
                        return a.get("id")
        return None

    # ------------------------------------------------------------------ pilotage

    def reach_my_turn(self, max_end_turns=12, force_cycle=False):
        """Enchaine des `endturn` jusqu'a mon tour. Purge au passage les flags de tour du caster
        (`StartTurnOperation$$ResetUnit`) ET ses `ChargedUnitIds` (vides par
        `FinishUnitTurnOperation$$Execute`) : l'etat de depart est donc « n'a pas bouge, n'a rien
        charge », ce qu'exige tout montage de charge.

        ⚠ `force_cycle=True` : passer par UN CYCLE COMPLET meme si c'est DEJA mon tour.

        CONFOND MESURE (case-ischarging-hits, reproduit deux fois a l'identique) : les `place()` du montage sont
        de VRAIS `MoveUnitOperation`, donc ils appellent `UpdateCharging` -- amener le caster d'une
        tuile a distance 2 vers une tuile adjacente a la cible CHARGE cette cible, avant meme le pas
        « officiel » du regime. Tant que `reach_my_turn` rendait la main sans aucun `endturn` (cas ou
        c'etait deja mon tour, typiquement apres un scenario precedent sur le MEME runner), cette
        charge residuelle SURVIVAIT au snapshot. Elle etait alors INVISIBLE cote offline (le seed de
        `UnitComponent+0x190` n'existait pas avant #230) -- l'ecart se lisait comme « le port
        n'applique pas le bonus » alors que c'est le MONTAGE qui avait triche. Signature exacte :
        regime `STEP_ADJACENT`, `charged=[]` offline mais le natif porte les coups de charge (mesure
        `C1_25`/31337 : live n=10, offline n=7). Le cycle force reste OBLIGATOIRE : depuis #230
        l'offline VOIT la charge residuelle, donc le montage ne se lit plus comme un bug de port --
        mais un regime `STEP_ADJACENT` qui porterait une charge residuelle mesurerait toujours
        `CHARGE`, c.-a-d. autre chose que ce que son nom promet.

        Le cycle force garantit un `FinishUnitTurnOperation$$Execute` sur le caster entre les
        placements et le snapshot -> liste VIDE, flag `Moved` purge, quel que soit l'ordre des
        scenarios sur un runner partage."""
        dv = self.dview()
        if self.my_player is None:
            mine = self.alive(dv)
            self.my_player = mine[0].get("owner") if mine else None
        if force_cycle and dv.get("currentPlayer") == self.my_player:
            # Sortir de mon tour : c'est CE `endturn` qui declenche le `FinishUnitTurn` de mes
            # unites, donc la purge des `ChargedUnitIds` posees par les placements.
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
            self.endturns += 1
            dv = self.dview()
        for _ in range(max_end_turns):
            if dv.get("currentPlayer") == self.my_player:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
            self.endturns += 1
            dv = self.dview()
        return dv if dv.get("currentPlayer") == self.my_player else None

    def place(self, unit_id, coord):
        """Pose `unit_id` sur `coord` (`applyAction` ne verifie NI propriete NI portee : les DEUX
        camps sont pilotables). RELIT la position -> True SSI le pas a reellement eu lieu.

        Chaque pose REUSSIE est tracee (`self.trace`) avec sa position de DEPART : un `place` est un
        `MoveUnitOperation` natif COMPLET, donc il appelle `UpdateCharging` et peut CHARGER une cible
        avant meme le pas du regime. La trace est ce qui permet de le voir."""
        before = next((x for x in self.alive() if x.get("id") == unit_id), None)
        from_pos = _upos(before) if before is not None else None
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": unit_id,
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
        u = next((x for x in self.alive() if x.get("id") == unit_id), None)
        moved = u is not None and _upos(u) == (int(coord[0]), int(coord[1]))
        self.trace.append((int(unit_id), from_pos, (int(coord[0]), int(coord[1])), bool(moved)))
        return moved

    def free_tiles(self, center, radius, exclude=()):
        """Tuiles MARCHABLES a distance hex EXACTEMENT `radius` de `center`, libres de toute unite
        vivante (hors `exclude`). Ordre deterministe (id de tuile croissant)."""
        occupied = {_upos(u) for u in self.alive() if u.get("id") not in set(exclude)}
        out = []
        for t in sorted(self.board.by_id):
            c = self.board.coord(t)
            if (self.board.walkable(t) and hexgeo.distance(tuple(center), c) == radius
                    and c not in occupied and c != tuple(center)):
                out.append(c)
        return out

    def snapshot(self):
        """Fige l'etat courant : `decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`."""
        return {
            "dv": self.dview(),
            "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 40),
            "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 60),
            "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 30),
        }

    # ------------------------------------------------------------------ montage des regimes

    def arrange(self, caster_visual, regime, enemy_index=0):
        """Impose la GEOMETRIE du regime demande et rend
        `{caster, target, start, step_to, regime}` (coordonnees (col,row)), ou None si la
        geometrie n'est pas realisable sur ce board.

        On DEPLACE les unites pour obtenir la configuration voulue -- jamais « bloque par la
        geometrie de spawn ». Les placements se font AVANT `reach_my_turn` (cf. protocole en tete).

          * `CHARGE`        : caster pose a distance 2 de la cible, pas vers une tuile adjacente.
          * `STEP_ADJACENT` : caster pose ADJACENT a la cible, pas vers une AUTRE tuile adjacente
                              a la MEME cible (la cible n'est donc jamais « nouvellement adjacente »).
          * `NO_STEP`       : caster pose adjacent, aucun pas (controle negatif).

        ⚠ ORDRE DES POSES -- NE PAS L'INVERSER (confond MESURE, case-ischarging-hits, reproduit 2x a l'identique).
        Un `place()` est un `MoveUnitOperation` natif COMPLET : il appelle `UpdateCharging`, qui
        ECRIT dans la liste `ChargedUnitIds` **DE L'UNITE QUI BOUGE**. Poser la cible d'abord puis
        amener le CASTER a cote d'elle fait donc CHARGER la cible **par le montage**, avant meme le
        pas du regime -- le regime mesure alors `CHARGE` sous le nom `STEP_ADJACENT`. Signature
        observee AVANT #230 (quand l'offline ne voyait pas la liste) : `charged=[]` offline mais le
        natif porte les coups de charge (`C1_25`/31337 : live n=10, offline n=7), ce qui se lisait
        comme « le port n'applique pas le bonus » alors que c'est le MONTAGE qui avait triche.
        Aucun `endturn` ne repare : la purge est `FinishUnitTurnOperation$$Execute`, PAR UNITE et sur
        son activation, pas une fin de tour d'equipe.

        L'ordre correct est donc : (1) GARER la cible LOIN de l'ancre, (2) ecarter les autres
        ennemis, (3) poser le CASTER (la cible est hors de portee d'adjacence -> sa liste reste
        vide), (4) AMENER la cible sur l'ancre -- c'est ELLE qui bouge, donc c'est SA liste qui est
        ecrite, et `IsCharging(caster, target)` ne lit que celle du CASTER.
        """
        dv = self.dview()
        me = self.by_visual(caster_visual, dv)
        if me is None:
            return None
        self.my_player = me.get("owner")
        ens = self.enemies_of(self.my_player, dv)
        if len(ens) <= enemy_index:
            return None
        tgt = ens[enemy_index]

        # Ancre la cible sur une tuile a 6 voisins marchables -> les deux regimes y tiennent.
        anchors = [self.board.coord(t) for t in sorted(self.board.by_id)
                   if self.board.walkable(t)
                   and len([c for c in self.free_tiles(self.board.coord(t), 1,
                                                       exclude=(tgt["id"], me["id"]))]) >= 3]
        for anchor in anchors:
            # (1) GARAGE de la cible : a distance hex >= 4 de l'ancre, donc a >= 2 de TOUTE tuile
            # que le caster occupera (ring1/ring2 de l'ancre) -> aucun pas du caster ne peut
            # l'ajouter a sa liste `ChargedUnitIds`. Si aucun garage n'existe, cette ancre est
            # inutilisable (on ne monte PAS un scenario qu'on ne peut pas garder honnete).
            park = self.free_tiles(anchor, 4, exclude=(tgt["id"],))
            if not park or not self.place(tgt["id"], park[0]):
                continue
            # (2) Les AUTRES ennemis sont ecartes : ni charges par le pas, ni encaisseurs de splash.
            for other in ens:
                if other["id"] == tgt["id"]:
                    continue
                far = self.free_tiles(anchor, 4, exclude=(other["id"],))
                if far:
                    self.place(other["id"], far[0])
            ring1 = self.free_tiles(anchor, 1, exclude=(me["id"], tgt["id"]))

            def _seal(start, step_to):
                """(3) caster pose, puis (4) la CIBLE rejoint l'ancre. Rend le plan, ou None."""
                if not self.place(me["id"], start):
                    return None
                if not self.place(tgt["id"], anchor):      # c'est la CIBLE qui bouge -> SA liste
                    return None
                return {"caster": me["id"], "target": tgt["id"], "start": start,
                        "step_to": step_to, "regime": regime, "anchor": anchor}

            if regime == CHARGE:
                ring2 = self.free_tiles(anchor, 2, exclude=(me["id"], tgt["id"]))
                for start in ring2:
                    for step_to in ring1:
                        if hexgeo.distance(start, step_to) != 1:
                            continue          # pas d'UN hex (portee de mouvement minimale)
                        plan = _seal(start, step_to)
                        if plan is not None:
                            return plan
            elif regime == STEP_ADJACENT:
                for start in ring1:
                    for step_to in ring1:
                        if step_to == start or hexgeo.distance(start, step_to) != 1:
                            continue
                        plan = _seal(start, step_to)
                        if plan is not None:
                            return plan
            else:   # NO_STEP
                for start in ring1:
                    plan = _seal(start, None)
                    if plan is not None:
                        return plan
        return None

    def run(self, caster_visual, regime, enemy_index=0, capture_mid=False):
        """Monte le regime, atteint mon tour, SNAPSHOTe, joue le pas puis l'ATTAQUE NORMALE en LIVE.

        Rend `{...arrange, snapshot, rng_after_step, live_per_hit, ability_type, moved}` ou None si
        la geometrie ou le tour n'ont pas pu etre obtenus. Le snapshot est pris AVANT le pas : c'est
        la seule facon d'avoir un offline qui rejoue LUI-MEME `UpdateCharging`.

        `capture_mid=True` ajoute une SECONDE capture, prise **APRES le pas et AVANT l'attaque** --
        donc MI-ACTIVATION, le seul instant ou `UnitComponent.ChargedUnitIds@+0x190` est non vide
        (`FinishUnitTurnOperation$$Execute` la vide a chaque fin d'activation). C'est la capture qui
        confronte le SEED de `load_state` (`snapshot._load_unit_turn_state`) plutot que le rejeu du
        pas. Cle `snapshot_mid` ; le `dumpRng` de `rng_after_step` est pris APRES elle, donc les deux
        voies offline partent du meme etat de PRNG que l'attaque live. `capture_mid=False` (defaut)
        laisse la sequence d'appels RPC STRICTEMENT inchangee."""
        self.trace, self.endturns = [], 0
        plan = self.arrange(caster_visual, regime, enemy_index=enemy_index)
        if plan is None:
            return None
        # `force_cycle=True` OBLIGATOIRE ici : les `place()` d'`arrange` chargent potentiellement la
        # cible (ce sont de vrais `MoveUnitOperation`). Sans cycle complet, cette charge residuelle
        # entre dans le snapshot cote LIVE et reste invisible cote OFFLINE. cf. `reach_my_turn`.
        if self.reach_my_turn(force_cycle=True) is None:
            return None
        # Re-verifie la geometrie APRES les endturns (une cascade a pu deplacer/tuer quelqu'un).
        dv = self.dview()
        pos = {u["id"]: _upos(u) for u in self.alive(dv)}
        if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) != plan["anchor"]:
            return None
        # GARDE DE REGIME -- la geometrie doit dire ce que le regime PROMET, sinon le verdict porte
        # sur autre chose que ce que le test croit mesurer :
        #   CHARGE        : depart NON adjacent, arrivee adjacente ;
        #   STEP_ADJACENT : depart DEJA adjacent, arrivee encore adjacente (rien de nouveau) ;
        #   NO_STEP       : adjacent, aucun pas.
        d0 = hexgeo.distance(plan["start"], plan["anchor"])
        d1 = hexgeo.distance(plan["step_to"], plan["anchor"]) if plan["step_to"] else d0
        expect = {CHARGE: (2, 1), STEP_ADJACENT: (1, 1), NO_STEP: (1, 1)}[regime]
        if (d0, d1) != expect:
            return None
        plan["ability_type"] = self.normal_attack_type(plan["caster"], dv)
        if plan["ability_type"] is None:
            return None
        plan["snapshot"] = self.snapshot()
        plan["moved"] = True
        if plan["step_to"] is not None:
            plan["moved"] = self.place(plan["caster"], plan["step_to"])
            if not plan["moved"]:
                return None
        if capture_mid:
            plan["snapshot_mid"] = self.snapshot()
        plan["rng_after_step"] = self.rpc("dumpRng", {"runnerId": self.rid}, 30)
        res = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": plan["caster"], "targetId": plan["target"],
            "abilityType": int(plan["ability_type"])}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        hits = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if ("Amount" in td and td.get("Attacker_Id") == plan["caster"]
                    and td.get("Target_Id") == plan["target"]):
                hits.append(int(td["Amount"]))
        plan["live_ok"] = bool(_ok(res) and a0.get("ok"))
        plan["live_per_hit"] = hits
        plan["live_raw"] = res
        plan["trace"] = list(self.trace)
        plan["endturns"] = self.endturns
        return plan

    # ------------------------------------------------------------------ rejeu offline

    def offline_state(self, rec):
        """Reconstruit un `State` OFFLINE depuis le snapshot PRE-pas, REJOUE le pas (donc
        `update_charging` + `set_moved_flag` sont poses PAR LE MOTEUR, pas declares), puis cale le MT
        sur le dump pris APRES le pas live. Rejouable : chaque appel rend un etat neuf."""
        s = rec["snapshot"]
        st = load_state(s["dv"], s["ob"], s["snap"], board=self.board)
        if rec.get("step_to") is not None:
            Runner(st).install_default_handlers().apply(
                MoveUnitMessage(rec["caster"], tuple(rec["step_to"])))
        dump = rec.get("rng_after_step") or s["rng"]
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = _seed_rng(dump)
        return st

    def replay_offline(self, rec):
        """Rejoue l'ATTAQUE NORMALE offline et rend
        `{per_hit, per_hit_all, additional, state, charged}`.

        `charged` = la liste `UnitComponent.ChargedUnitIds` du caster APRES le pas (le 2e terme de
        `BattleQuery$$IsCharging`).

        ⚠ `per_hit` NE PORTE QUE LES COUPS D'ARME, et c'est structurel : `damage_ops/normal.py`
        range les sous-operations du canal #179 (COUPS ADDITIONNELS HETEROGENES) dans une cle
        SEPAREE (`additional_hits`), parce que le natif en fait lui aussi des operations distinctes
        (`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`,
        frere du groupe d'arme). Le LIVE, lui, ne distingue pas : le harnais compte TOUT evenement
        de degat caster -> cible, coups additionnels COMPRIS. Comparer `per_hit` a `live_per_hit`
        sur un porteur du canal #179 rend donc un ecart QUI N'EN EST PAS UN -- mesure #1065,
        `FragLanceEffect` : live n=5, `per_hit` n=4, le 5e coup etant dans `additional_hits`.
        `per_hit_all` concatene les deux DANS L'ORDRE DE MATERIALISATION (arme d'abord, canal #179
        ensuite -- l'ordre natif, `prev`-threade), et c'est LUI qu'on confronte au live.
        `per_hit` reste inchange pour les appelants qui ne mesurent que l'arme."""
        from engine.runner.components import UnitComponent
        st = self.offline_state(rec)
        e = st.get_entity(rec["caster"])
        uc = e.get_component(UnitComponent) if e is not None else None
        charged = sorted(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else []
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
        last = runner.damage_handler.last or {}
        per_hit = list(last.get("per_hit") or [])
        add = last.get("additional_hits") or {}
        add_hits = list(add.get("per_hit") or [])
        return {"per_hit": per_hit, "per_hit_all": per_hit + add_hits, "additional": add,
                "state": st, "charged": charged}

    # ------------------------------------------------------------ rejeu depuis la capture MI-ACTIVATION

    def offline_state_mid(self, rec, seeded=True):
        """Reconstruit un `State` OFFLINE depuis la capture **MI-ACTIVATION** (`snapshot_mid`, prise
        APRES le pas). AUCUN move n'est rejoue : `charged_unit_ids` vient donc du SEED
        (`combatSnapshot.units[].chargedUnitIds` -> `snapshot._load_unit_turn_state`), pas du moteur.

        C'est la voie EXACTEMENT COMPLEMENTAIRE d'`offline_state` : celle-ci confronte le SEED, celle-la
        confronte le mirror d'`UpdateCharging`. Les deux doivent rendre le meme verdict que le natif.

        `seeded=False` REJOUE l'etat d'AVANT le cablage (#230) : on efface les deux champs juste apres
        le chargement. Sert de contre-epreuve -- si le scenario est discriminant, ce mode DIVERGE du
        live ; s'il ne diverge pas, la mesure ne prouve rien (le montage etait vacu.)"""
        from engine.runner.components import UnitComponent
        s = rec.get("snapshot_mid")
        if s is None:
            raise AssertionError("run(capture_mid=True) est requis pour rejouer depuis la mi-activation")
        st = load_state(s["dv"], s["ob"], s["snap"], board=self.board)
        if not seeded:
            for ent in st.entities.values():
                uc = ent.get_component(UnitComponent)
                if uc is not None:
                    uc.charged_unit_ids = []
                    uc.current_turn_start_tile = None
        dump = rec.get("rng_after_step") or s["rng"]
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = _seed_rng(dump)
        return st

    def replay_offline_mid(self, rec, seeded=True):
        """Rejoue l'ATTAQUE NORMALE depuis la capture MI-ACTIVATION. Meme retour que
        `replay_offline` (`per_hit` / `state` / `charged`)."""
        from engine.runner.components import UnitComponent
        st = self.offline_state_mid(rec, seeded=seeded)
        e = st.get_entity(rec["caster"])
        uc = e.get_component(UnitComponent) if e is not None else None
        charged = sorted(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else []
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
        per_hit = list((runner.damage_handler.last or {}).get("per_hit") or [])
        return {"per_hit": per_hit, "state": st, "charged": charged}

    def dispose(self):
        self.rpc("disposeRunner", {"runnerId": self.rid}, 20)


@pytest.fixture(scope="session")
def charge_regime(rpc, build_runner):
    """FABRIQUE de `ChargeRegimeHarness` -- fixture NOMMEE, reutilisable par tout test de charge.

    `make(p_units=..., a_units=..., seed=..., board=..., extra=[...])`. Le `--board` est OBLIGATOIRE
    au build ; defaut `MC1_67` (arene). Les PV sont gonfles par defaut pour qu'aucune cible ne meure
    en cours de montage (un cadavre change la geometrie ET le flux d'evenements)."""
    def make(p_units, a_units, seed="777", board="MC1_67", extra=None):
        args = ["--p-units", p_units, "--a-units", a_units,
                "--hp-target", "120000", "--hp-player", "120000", "--no-ai", *(extra or [])]
        rid = build_runner(seed, extra=args, board=board)["rid"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        if not _ok(h.dview()):
            pytest.skip("decisionView KO")
        return h
    return make
