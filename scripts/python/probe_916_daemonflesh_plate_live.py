"""#916 -- CONFRONT LIVE de la relique `DaemonfleshPlate` (`TriggeredAbilityType` 1493).

Ce que le probe MESURE, etage par etage (jamais un scalaire ajuste) :

  1. **MONTAGE** -- la relique est-elle REELLEMENT montee ? Garde LUE dans `unitAbilityStates` :
     une entree `triggered` dont `raw[0] == 1493` et `raw[10] == 3` (hierarchie TERTIAIRE), avec le
     `level` demande. Les trois ecritures de #237 echouent DEUX FOIS EN SILENCE ; sans cette garde
     on mesurerait une unite SANS relique et l'accord serait vide de sens.
  2. **SEQUENCE D'ARMURE** -- `combatSnapshot.units[].stats.fixedArmor` du porteur apres CHAQUE
     attaque. C'est l'observable qui tranche les DEUX questions que le decompile seul ne ferme pas :
       * l'effet 1490 EMPILE-t-il (`k x extraArmor`) ou est-il RAFRAICHI (`extraArmor` constant) ?
         Le natif ne le dit que par le slot 5 de l'`IEffect` que
         `IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect` consulte, valeur runtime
         derriere la metadata IL2CPP -- donc une MESURE, pas une deduction ;
       * le seuil est-il `>= nrOfAttacks - 1` (reset a la N-ieme attaque, max `(N-1) x extraArmor`)
         ou `>= nrOfAttacks` ? Un decalage d'UNE attaque, invisible de tout accord agrege.
  3. **RE-ARMEMENT DE L'ACTIVE** -- l'active du porteur est CONSOMMEE avant la serie
     (`state.usable = false`, `lastTurnUsed` pose) ; a l'attaque de reset elle doit redevenir
     `usable = true, lastTurnUsed = null`. C'est le seul observable du volet
     `DaemonfleshPlate_ResetActiveAbility` : l'effet 1491 est pose ET consomme DANS LA MEME
     `applyAction` (le `PhaseEnd` clot le message top-level), donc il n'est jamais visible dans un
     `decisionView` pris entre deux actions.
  4. **ACCORD PORT/NATIF** -- la meme sequence, rejouee OFFLINE par les vecteurs du port
     (`finish_attack_triggers` = `On(9)`, puis `phase_end_triggers` = `On(0x3a)`), depuis le `State`
     charge AVANT la premiere attaque.
  5. **MUTANTS** -- sept mutations du port, chacune avec son verdict ATTENDU. Un mutant qui ne mord
     pas nomme un temoin AVEUGLE ; c'est l'instrument, pas la decoration.

BRAS (`--bras`) :
  * `NOMINAL`    -- niveau 1 : `extraArmor = 145`, `nrOfAttacks = 8`.
  * `NIVEAU6`    -- niveau 6 : `extraArmor = 184`, `nrOfAttacks = 7`. Il discrimine DEUX choses d'un
                    coup : le palier de `nrOfAttacks` (8 -> 7, la seule variable du gameconfig qui
                    CHANGE de palier) et le fait que le niveau lu est bien le TERTIAIRE -- un port
                    qui lirait le niveau PASSIF (50 sur tout runner normalise) rendrait le DERNIER
                    palier dans les deux bras et ne verrait aucune difference.
  * `SPECTATEUR` -- la relique est sur une SECONDE unite de mon camp, qui n'attaque PAS ; c'est
                    l'autre qui frappe. Le gate `get_OwnerIsCaster` doit FERMER le canal : le
                    porteur ne doit gagner AUCUNE armure. Sans ce bras, le gate n'est exerce par
                    AUCUN regime nominal (porteur == attaquant par construction).

Discipline : un runner par bras, dispose aussitot ; `--state-file` unique ; ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

ABILITY_ID = "DaemonfleshPlate"
CARRIER = "blackTerminator"        # porteur `lineup` de la relique, AU POOL
SPECTATOR = "worldTerminator"      # 2e porteur autorise, AU POOL -- bras `get_OwnerIsCaster`
TARGET = "astraBullgryn"           # cible-sac, PV forces
ACTIVE_OF_CARRIER = 1022           # `ActiveAbilityType.BringerOfDespair` -- l'active re-armee
EXTRA_ARMOR_KEY = "extraArmor"     # `AbilityVariableType` 0x1b = 27
NR_OF_ATTACKS_KEY = "nrOfAttacks"  # `AbilityVariableType` 0x4e = 78
TRIGGERED_ID = 1493                # `TriggeredAbilityType.DaemonfleshPlate`
HIERARCHY_TERTIARY = 3             # `UnitFactory$$AddConfiguredAbilities`, branche TERTIAIRE


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un montage muet."""


def paliers(var_key: str) -> list:
    """Paliers RELUS du gameconfig -- jamais codes en dur, meme lecture que le port."""
    import gameconfig as GC
    arr = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(var_key)
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ABILITY_ID, var_key))
    return [int(x) for x in arr]


def garde_regime(level: int, p_armor: list, p_atk: list) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage -- chacune ferme une porte de vert-qui-ne-mesure-rien.

      * niveau hors paliers -> `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au dernier
        palier et le bras NIVEAU ne discrimine plus rien ;
      * `nrOfAttacks <= 1` -> le seuil `>= N-1` vaudrait `>= 0`, VRAI des la premiere attaque : la
        branche ELSE ne serait JAMAIS prise et l'empilement serait inobservable ;
      * `extraArmor <= 0` -> l'empilement n'aurait AUCUN observable sur `fixedArmor`.
    """
    if not (1 <= level <= len(p_armor)) or not (1 <= level <= len(p_atk)):
        raise SystemExit("niveau %d hors des paliers (%d/%d) : le clamp haut de "
                         "`TryGetVariableArrayForLevel` rendrait le bras NIVEAU non discriminant"
                         % (level, len(p_armor), len(p_atk)))
    if p_atk[level - 1] <= 1:
        raise SystemExit("nrOfAttacks[%d] = %d : le seuil `>= N-1` serait VRAI des la 1re attaque, "
                         "la branche ELSE (l'empilement) ne serait jamais prise"
                         % (level, p_atk[level - 1]))
    if p_armor[level - 1] <= 0:
        raise SystemExit("extraArmor[%d] = %d : aucun observable sur fixedArmor"
                         % (level, p_armor[level - 1]))


def porteur_de(bras: str) -> str:
    """Qui EQUIPE la relique. Dans le bras SPECTATEUR c'est une SECONDE unite de mon camp, pas
    l'attaquant -- c'est tout l'objet du bras."""
    return SPECTATOR if bras == "SPECTATEUR" else CARRIER


def p_units_de(bras: str) -> str:
    return "%s,%s" % (CARRIER, SPECTATOR) if bras == "SPECTATEUR" else CARRIER


def flags_de_build(bras: str, level: int) -> list:
    """FOYER UNIQUE des flags de montage, partage par le probe et par son cliquet
    (`tests/engine/runner/test_916_daemonflesh_plate_live.py`) : un montage DUPLIQUE derive de son
    original sans que rien ne le signale.

    ⚠ `--hp-player`/`--hp-target` mettent `Armor`/`FixedArmor` a 0 des DEUX cotes : la base d'armure
    du porteur est donc NULLE, et `fixedArmor` mesure EXACTEMENT la contribution de la relique -- pas
    un delta a soustraire d'un socle qu'on n'aurait pas mesure. Ils font AUSSI durer la bataille
    assez longtemps pour jouer les `nrOfAttacks + 2` actions de la serie.

    ⚠ `--crit 0,0` / `--block-target 0,0` : un CRIT ou un BLOCK ne changent rien au compteur (le
    behaviour ne lit ni l'un ni l'autre), mais ils peuvent TUER la cible-sac et interrompre la serie.
    On les eteint pour que le montage ne depende d'aucun tirage."""
    return ["--equip-relic", "%s:%s:%d" % (porteur_de(bras), ABILITY_ID, level),
            "--hp-target", "900000", "--hp-player", "900000", "--no-ai",
            "--crit", "0,0", "--block-target", "0,0"]


def build(a, bras: str, level: int):
    """Un runner par bras, dispose aussitot (le budget est partage)."""
    fd, sf = tempfile.mkstemp(prefix="probe_916_%s_l%d_" % (bras, level), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = ([sys.executable, "rl_duel.py", "build",
             "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
             "--p-units", p_units_de(bras), "--a-units", TARGET] + flags_de_build(bras, level))
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (bras, (p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


class Live:
    """Pilotage minimal d'un runner (les DEUX camps sont pilotables : `applyAction` ne verifie ni
    propriete ni portee)."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board
        self.mine = None

    def dview(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)

    def alive(self, dv=None):
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, v, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == v), None)

    def stats(self, eid):
        snap = self.rpc("combatSnapshot", {"runnerId": self.rid}, 60)
        for u in (snap.get("units") or []):
            if u.get("entityId") == eid:
                return u.get("stats") or {}
        return {}

    def snapshot(self):
        return {"dv": self.dview(),
                "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 40),
                "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 60)}

    def ability_state(self, eid, ability_type):
        uas = self.rpc("unitAbilityStates", {"runnerId": self.rid}, 40)
        for u in (uas.get("units") or []):
            if u.get("entityId") == eid:
                for x in (u.get("actives") or []):
                    if x.get("type") == ability_type:
                        s = x.get("state") or {}
                        return {"usable": s.get("usable"), "lastTurnUsed": s.get("lastTurnUsed")}
        return None

    def tertiary_raw(self, eid):
        """L'entree TERTIAIRE du canal `unitAbilityStates` : `(abilityId, level, hierarchie)`.
        TRI-ETAT -- `None` = canal muet pour cette unite (jamais un tuple neutre qui se lirait
        « pas de relique »)."""
        uas = self.rpc("unitAbilityStates", {"runnerId": self.rid}, 40)
        for u in (uas.get("units") or []):
            if u.get("entityId") != eid:
                continue
            trig = u.get("triggered")
            if trig is None:
                return None
            for e in trig:
                raw = e.get("raw") or []
                if len(raw) >= 11 and int(raw[0]) == TRIGGERED_ID:
                    return (int(raw[0]), int(e.get("level") or 0), int(raw[10]))
            return ()
        return None

    def my_turn(self, max_end_turns=12):
        for _ in range(max_end_turns):
            dv = self.dview()
            if dv.get("currentPlayer") == self.mine:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
        return None

    def place(self, uid, coord):
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": uid,
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
        u = next((x for x in self.alive() if x.get("id") == uid), None)
        return u is not None and _pos(u) == (int(coord[0]), int(coord[1]))

    def normal_attack_type(self, uid):
        for u in (self.dview().get("units") or []):
            if u.get("id") == uid:
                for x in (u.get("abilities") or []):
                    if x.get("kind") == "normal":
                        return x.get("id")
        return None

    def cast(self, caster, target, ability_type):
        r = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": target,
            "abilityType": ability_type}}, 60)
        return (r.get("actions") or [{}])[0] or {}

    def endturn(self):
        self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)

    def dispose(self):
        try:
            self.rpc("disposeRunner", {"runnerId": self.rid}, 40)
        except Exception:
            pass


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def stage(h, bras: str, level: int):
    """Amene la geometrie (attaquant AU CONTACT de la cible), verifie le MONTAGE de la relique, fige
    le snapshot de depart. On DEPLACE les unites -- jamais << bloque par la geometrie de spawn >>."""
    import hexgeo
    dv = h.dview()
    att = h.by_visual(CARRIER, dv)
    if att is None:
        raise MontageError("attaquant %s absent du decisionView" % CARRIER)
    h.mine = att.get("owner")
    dv = h.my_turn()
    if dv is None:
        raise MontageError("le tour de l'attaquant est inatteignable")
    att = h.by_visual(CARRIER, dv)
    tgt = h.by_visual(TARGET, dv)
    porteur_vis = porteur_de(bras)
    porteur = h.by_visual(porteur_vis, dv)
    if att is None or tgt is None or porteur is None:
        raise MontageError("attaquant / cible / porteur absent du decisionView")

    raw = h.tertiary_raw(porteur["id"])
    if raw is None:
        raise MontageError("canal `unitAbilityStates.triggered` MUET pour le porteur -- "
                           "aucune mesure possible (tri-etat)")
    if raw == () or raw[0] != TRIGGERED_ID or raw[2] != HIERARCHY_TERTIARY or raw[1] != level:
        raise MontageError("relique NON montee comme attendu sur %s : lu %r, attendu "
                           "(%d, %d, %d) -- les trois ecritures de #237 echouent DEUX FOIS "
                           "EN SILENCE" % (porteur_vis, raw, TRIGGERED_ID, level, HIERARCHY_TERTIARY))
    if bras == "SPECTATEUR":
        # CONTROLE NEGATIF : l'ATTAQUANT ne doit PAS porter la relique, sinon le gate qu'on croit
        # exercer serait satisfait par lui-meme et le bras ne mesurerait rien.
        r2 = h.tertiary_raw(att["id"])
        if r2 is None:
            raise MontageError("canal muet pour l'attaquant -- controle negatif impossible")
        if r2 != ():
            raise MontageError("l'ATTAQUANT porte lui aussi la relique (%r) : le bras SPECTATEUR "
                               "ne mesurerait rien" % (r2,))

    # cible AU CONTACT de l'attaquant
    apos = _pos(att)
    occupied = {_pos(u) for u in h.alive() if u.get("id") != tgt["id"]}
    cands = [h.board.coord(t) for t in sorted(h.board.by_id)
             if h.board.walkable(t) and hexgeo.distance(tuple(apos), h.board.coord(t)) == 1
             and h.board.coord(t) not in occupied]
    if not cands:
        raise MontageError("aucune tuile libre adjacente a l'attaquant")
    if not h.place(tgt["id"], cands[0]):
        raise MontageError("le placement de la cible a echoue")
    na = h.normal_attack_type(att["id"])
    if na is None:
        raise MontageError("attaque normale introuvable pour l'attaquant")
    return {"att": att["id"], "tgt": tgt["id"], "porteur": porteur["id"],
            "porteur_vis": porteur_vis, "na": na, "snapshot": h.snapshot()}


def attendus(bras: str, ea: int, nr: int, n: int):
    """Les DEUX sequences ATTENDUES, DERIVEES du RE -- foyer partage probe/cliquet.

    ARMURE : `k x extraArmor` pour `k = 1..N-1`, puis **0** a la N-ieme action (la branche THEN
    retire les N-1 piles d'un coup), puis le cycle REPART. Le maximum est donc `(N-1) x extraArmor`,
    PAS `N x extraArmor` -- c'est le `Subtract(ConfigVar(nrOfAttacks), DSLFormulas+0x20 = Direct(1))`
    du seuil.

    ACTIVE : consommee par le cast en tete de serie, elle redevient utilisable EXACTEMENT a la
    N-ieme action (celle qui pose 1491) et le reste.

    Bras SPECTATEUR : le gate `get_OwnerIsCaster` ferme le canal -> armure NULLE partout."""
    if bras == "SPECTATEUR":
        return [0] * n, None
    armure = [ea * k for k in range(1, nr)] + [0] + [ea * k for k in range(1, n - nr + 1)]
    active = [False] * (nr - 1) + [True] * (n - nr + 1)
    return armure, active


def serie_live(h, rec, n: int, active_en_tete: bool):
    """`n` ACTIONS OFFENSIVES du CARRIER sur la cible. Rend `(armures, usables)` du PORTEUR.

    ⚠ `active_en_tete` : la 1re action est le CAST de l'active du porteur, PAS une attaque normale --
    et elle COMPTE dans la serie. C'est une MESURE, pas un choix de confort : `On(9 = Attack)` est
    l'evenement GENERIQUE de fin d'attaque, emis par `FinishAttackOperation` pour l'attaque normale
    COMME pour une ability offensive. Mesure : compteur a 2 (armure 290), cast de l'active -> 3 crans,
    puis 4, 5, 6, 7, puis reset. Traiter le cast comme << hors serie >> decalerait l'attendu d'un
    cran et ferait lire un port juste comme faux.

    C'est ce cast qui CONSOMME l'active (`usable -> false`), donc qui rend le volet
    `DaemonfleshPlate_ResetActiveAbility` OBSERVABLE : sans lui, l'active est deja utilisable et le
    gate `EntityCanHaveActiveAbilityReset` refuserait tout reset -- un vert qui ne mesure rien."""
    armures, usables = [], []
    for i in range(n):
        if h.my_turn() is None:
            raise MontageError("tour inatteignable en cours de serie")
        ab = ACTIVE_OF_CARRIER if (active_en_tete and i == 0) else rec["na"]
        a0 = h.cast(rec["att"], rec["tgt"], ab)
        if not a0.get("ok"):
            raise MontageError("action %d (ability %s) REFUSEE : %s"
                               % (i + 1, ab, json.dumps(a0)[:300]))
        armures.append(int(h.stats(rec["porteur"]).get("fixedArmor") or 0))
        st = h.ability_state(rec["porteur"], ACTIVE_OF_CARRIER)
        usables.append(None if st is None else bool(st.get("usable")))
        h.endturn()
    return armures, usables


# ------------------------------------------------------------------ rejeu OFFLINE (le port)

def serie_offline(board, rec, n: int, mutant: str = None, active_consommee: bool = False):
    """Rejoue la MEME serie par les VECTEURS du port -- `On(9)` puis `On(0x3a)`, c'est-a-dire
    exactement ce que `Runner.apply` enchaine pour une attaque : `finish_attack_triggers` a la
    sortie d'`AttackDamageOperation`, `phase_end_triggers` a la cloture du message top-level.

    Le degat n'est PAS rejoue : il n'entre dans AUCUN etage de cette mecanique (le behaviour ne lit
    ni PV ni profil). Rejouer le pipeline complet ajouterait du bruit sans rien mesurer de plus.

    `active_consommee` pose `can_still_be_used = False` sur les actives du porteur AVANT la boucle --
    l'etat que le cast d'active produit cote live. Sans lui,
    `BattleQuery$$EntityCanHaveActiveAbilityReset` rend FAUX (rien a re-armer) et le volet RESET
    serait un vert vide : le mutant `RESET_NOGATE` ne pourrait pas mordre.

    Rend `(armures, usables)` -- deux canaux d'observation distincts."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, ActiveAbilitiesComponent
    from engine.runner.operations.triggers.dispatch.attack import finish_attack_triggers
    from engine.runner.operations.triggers.dispatch.phase import phase_end_triggers
    from engine.entities.stats import StatType
    s = rec["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    if active_consommee:
        e0 = st.get_entity(rec["porteur"])
        comp = e0.get_component(ActiveAbilitiesComponent) if e0 is not None else None
        for ab in (comp.abilities if comp is not None else ()):
            ab.can_still_be_used = False
    undo = _mute(mutant, st) if mutant else None
    try:
        armures, usables = [], []
        for _ in range(n):
            finish_attack_triggers(st, rec["att"], rec["tgt"], ranged=False)
            phase_end_triggers(st)
            e = st.get_entity(rec["porteur"])
            sc = e.get_component(StatsComponent) if e is not None else None
            armures.append(int(sc.ctx.stat(StatType.FIXED_ARMOR) or 0) if sc is not None else 0)
            comp = e.get_component(ActiveAbilitiesComponent) if e is not None else None
            usables.append(None if comp is None
                           else all(bool(ab.can_still_be_used) for ab in comp.abilities))
        return armures, usables
    finally:
        if undo is not None:
            undo()


def _mute(nom: str, st):
    """Installe une MUTATION du port et rend le callable qui la retire. Chaque mutant a un verdict
    ATTENDU (cf. `MUTANTS`) ; un mutant qui NE MORD PAS nomme un temoin aveugle."""
    import engine.runner.operations.triggers.loki.daemonflesh_plate as DFP
    from engine.entities.effects.loki.daemonflesh_plate import DaemonfleshPlateExtraArmorEffect
    from engine.entities.behaviours import If, op_and
    from engine.entities.triggers import AmountIsEqualOrGreater
    from engine.entities.formulas import Difference, GetPersistentData
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import Owner
    from engine.entities.selectors.tiles import Caster
    from engine.entities.stats import StatType
    from engine.entities.effect_type import EffectType
    from engine.runner.abilities.behaviours.effects import (AddEffect, AddStaticStatModifierEffect,
                                                            RemoveEffect)
    from engine.runner.abilities.behaviours.persistent_data import (AddPersistentData,
                                                                    ClearPersistentData)
    orig_tree = DFP.daemonflesh_plate_behaviour_tree
    orig_state = DFP.triggered_ability_state
    orig_matches = DFP.DaemonfleshPlateAbility.matches
    orig_reset_matches = DFP.DaemonfleshPlateResetActiveAbility.matches
    orig_stack = DaemonfleshPlateExtraArmorEffect.stacks_stat_mod_on_add

    def _arbre(extra_armor, nr, seuil_delta=1, increment=1, avec_clear=True):
        counter = GetPersistentData(DFP.DAEMONFLESH_PLATE, Owner(), DFP._COUNTER_KEY)
        cond = AmountIsEqualOrGreater(counter, Difference(Const(int(nr)), Const(int(seuil_delta))))
        then_ = op_and(RemoveEffect(DFP.EXTRA_ARMOR_EFFECT, Owner()),
                       AddEffect(DFP.RESET_ACTIVE_EFFECT,
                                 EffectType.DaemonfleshPlate_ResetActive.name, Owner(),
                                 duration_rounds=None, source_ref=Owner()))
        if avec_clear:
            then_ = op_and(then_, ClearPersistentData(DFP.DAEMONFLESH_PLATE, Owner(),
                                                     DFP._COUNTER_KEY))
        else_ = op_and(
            AddStaticStatModifierEffect(Caster(), DFP.EXTRA_ARMOR_EFFECT,
                                        int(StatType.FIXED_ARMOR), int(extra_armor),
                                        name=EffectType.DaemonfleshPlate_ExtraArmor.name),
            AddPersistentData(DFP.DAEMONFLESH_PLATE, Owner(), DFP._COUNTER_KEY, int(increment)))
        return If(cond, then_, else_)

    if nom == "SEUIL_N":            # `>= N` au lieu de `>= N - 1`
        DFP.daemonflesh_plate_behaviour_tree = lambda ea, nr: _arbre(ea, nr, seuil_delta=0)
    elif nom == "NOCLEAR":          # la branche THEN ne vide plus le compteur
        DFP.daemonflesh_plate_behaviour_tree = lambda ea, nr: _arbre(ea, nr, avec_clear=False)
    elif nom == "INCREMENT_2":      # `AddPersistentData(2)` au lieu de `DSLFormulas+0x20 = Direct(1)`
        DFP.daemonflesh_plate_behaviour_tree = lambda ea, nr: _arbre(ea, nr, increment=2)
    elif nom == "NOSTACK":          # l'effet 1490 n'empile plus (gate << deja-present >> retabli)
        DaemonfleshPlateExtraArmorEffect.stacks_stat_mod_on_add = False
    elif nom == "NIVEAU_PASSIF":    # lire le couple PASSIF au lieu du TERTIAIRE
        def _passif(state, uid, name):
            from engine.runner.components import StatsComponent as SC
            e = state.get_entity(uid)
            sc = e.get_component(SC) if e is not None else None
            ctx = sc.ctx if sc is not None else None
            if ctx is None:
                return (None, 100)
            return (getattr(ctx, "passive_ability_level", None),
                    int(getattr(ctx, "ability_variables_multiplier", 100) or 100))
        DFP.triggered_ability_state = _passif
    elif nom == "OWNERISCASTER_OFF":   # le gate `get_OwnerIsCaster` est neutralise
        DFP.DaemonfleshPlateAbility.matches = lambda self, state, ev: True
    elif nom == "RESET_NOGATE":        # `HasEffect(Owner, 1491)` neutralise
        DFP.DaemonfleshPlateResetActiveAbility.matches = lambda self, state, ev: True
    else:
        raise SystemExit("mutant inconnu : %s" % nom)

    def undo():
        DFP.daemonflesh_plate_behaviour_tree = orig_tree
        DFP.triggered_ability_state = orig_state
        DFP.DaemonfleshPlateAbility.matches = orig_matches
        DFP.DaemonfleshPlateResetActiveAbility.matches = orig_reset_matches
        DaemonfleshPlateExtraArmorEffect.stacks_stat_mod_on_add = orig_stack
    return undo


#: `(mutant, mord sur le canal ARMURE ?, mord sur le canal ACTIVE ?)` -- bras NOMINAL / NIVEAU6.
#: Chaque attente est DERIVEE de la structure de l'arbre, jamais du resultat observe :
#:  * `SEUIL_N` (`>= N` au lieu de `>= N-1`) DECALE le reset d'une action -> les DEUX canaux ;
#:  * `NOCLEAR` : le compteur reste >= N-1 pour toujours -> la branche THEN est prise a CHAQUE
#:    action a partir de la N-ieme. L'ARMURE ne repart donc jamais (elle reste a 0), mais l'ACTIVE
#:    est re-armee a la N-ieme *et le reste* -- exactement la sequence nominale : ce canal-la ne
#:    peut PAS distinguer, et le dire est le point du mutant ;
#:  * `INCREMENT_2` : le compteur monte deux fois plus vite -> reset premature, les DEUX canaux ;
#:  * `NOSTACK` : seule la MAGNITUDE plafonne (le compteur, lui, est intact) -> le reset reste a la
#:    N-ieme action, canal ACTIVE inchange ;
#:  * `NIVEAU_PASSIF` : le niveau passif d'un runner normalise est 50, que
#:    `TryGetVariableArrayForLevel` CLAMPE au DERNIER palier. Son effet sur le canal ACTIVE est donc
#:    **DERIVE, pas constant** : il ne deplace le reset que si `nrOfAttacks[niveau] != nrOfAttacks[-1]`
#:    -- VRAI au niveau 1 (8 vs 7), FAUX au niveau 6 (7 vs 7, palier deja au plancher). Le canal
#:    ARMURE, lui, mord toujours (`extraArmor` est STRICTEMENT croissant sur les 10 paliers).
#:    Cette attente est donc CALCULEE dans `mutants_pour` ; l'ecrire en dur ferait rougir le bras
#:    NIVEAU6 sur une DEGENERESCENCE du gameconfig, pas sur un defaut du port ;
#:  * `OWNERISCASTER_OFF` : porteur == attaquant, le gate est deja VRAI -> aucun canal. C'est le
#:    CONTROLE NEGATIF, et c'est le bras SPECTATEUR qui exerce vraiment ce gate ;
#:  * `RESET_NOGATE` : ne touche pas l'arbre de l'ability principale -> armure inchangee ; l'active
#:    est re-armee des la 1re phase -> canal ACTIVE seul.
def mutants_pour(bras: str, level: int, p_armor: list, p_atk: list):
    """La table des attentes, DERIVEE du gameconfig la ou elle en depend (cf. `NIVEAU_PASSIF`).

    Dans le bras SPECTATEUR, l'attaquant n'est PAS le porteur et aucun cast d'active n'ouvre la
    serie : le canal ACTIVE n'y est pas arme, seul l'ARMURE mesure."""
    if bras == "SPECTATEUR":
        return [("OWNERISCASTER_OFF", True, False)]
    # le repli PASSIF clampe au dernier palier -> il ne deplace le reset que si le palier DIFFERE
    passif_deplace_le_reset = (p_atk[level - 1] != p_atk[-1])
    return [("SEUIL_N", True, True), ("NOCLEAR", True, False), ("INCREMENT_2", True, True),
            ("NOSTACK", True, False),
            ("NIVEAU_PASSIF", p_armor[level - 1] != p_armor[-1], passif_deplace_le_reset),
            ("OWNERISCASTER_OFF", False, False), ("RESET_NOGATE", False, True)]


def run_bras(a, rpc, Board, bras: str, level: int, p_armor: list, p_atk: list) -> int:
    rid, sf = build(a, bras, level)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    ea, nr = p_armor[level - 1], p_atk[level - 1]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Live(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        try:
            rec = stage(h, bras, level)
        except MontageError as e:
            print("[%s/l%d] REFUS : %s" % (bras, level, e))
            return 2
        n = nr + 2                      # deux actions APRES le reset -> le cycle doit REPARTIR
        actif = (bras != "SPECTATEUR")
        try:
            armures, usables = serie_live(h, rec, n, active_en_tete=actif)
        except MontageError as e:
            print("[%s/l%d] REFUS : %s" % (bras, level, e))
            return 2

        att_armure, att_us = attendus(bras, ea, nr, n)
        off_a, off_u = serie_offline(h.board, rec, n, active_consommee=actif)
        accord = (off_a == armures)
        conforme = (armures == att_armure)
        rc = 0 if (accord and conforme) else 1
        print("[%s/l%d] extraArmor=%d nrOfAttacks=%d" % (bras, level, ea, nr))
        print("   armure natif  : %s" % armures)
        print("   armure port   : %s   accord=%s" % (off_a, accord))
        print("   armure attendu: %s   conforme=%s" % (att_armure, conforme))

        if actif:
            # Volet RESET. Le cast d'active EN TETE de serie l'a consommee ; elle doit redevenir
            # utilisable EXACTEMENT a l'action de reset (la nr-ieme), pas avant.
            ok_live = (usables == att_us)
            ok_port = (off_u == att_us)
            rc |= 0 if (ok_live and ok_port) else 1
            print("   active natif  : %s   conforme=%s" % (usables, ok_live))
            print("   active port   : %s   conforme=%s" % (off_u, ok_port))

        for nom, mord_a, mord_u in mutants_pour(bras, level, p_armor, p_atk):
            m_a, m_u = serie_offline(h.board, rec, n, mutant=nom, active_consommee=actif)
            got_a, got_u = (m_a != off_a), (m_u != off_u)
            if got_a != mord_a or got_u != mord_u:
                rc |= 1
            print("   mutant %-18s armure=%-5s (att %-5s) active=%-5s (att %-5s)  %s"
                  % (nom, got_a, mord_a, got_u, mord_u, m_a))
        return rc
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 40)
        except Exception:
            pass
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bras", default="NOMINAL,NIVEAU6,SPECTATEUR")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    p_armor, p_atk = paliers(EXTRA_ARMOR_KEY), paliers(NR_OF_ATTACKS_KEY)
    print("== #916 %s -- porteur %s, cible %s" % (ABILITY_ID, CARRIER, TARGET))
    print("   paliers extraArmor  : %s" % p_armor)
    print("   paliers nrOfAttacks : %s" % p_atk)
    if len(set(p_atk)) < 2:
        print("   [note] nrOfAttacks est CONSTANT sur les paliers : le bras NIVEAU6 ne discrimine "
              "plus que la MAGNITUDE, plus le seuil.")

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # CANAL RELIQUE : sans transport ambiant, `UnitContext.tertiary_ability` reste None et
    # `triggered_ability_state` retombe sur le couple PASSIF -> le niveau lu serait 50.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)

    rc = 0
    for bras in [b.strip() for b in a.bras.split(",") if b.strip()]:
        level = 6 if bras == "NIVEAU6" else 1
        garde_regime(level, p_armor, p_atk)
        rc |= run_bras(a, rpc, Board, bras, level, p_armor, p_atk)
    print("== rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
