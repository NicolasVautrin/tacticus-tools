"""#1012 -- CONFRONT LIVE de la relique `Dw02AdvancedBurstCannon` (`TriggeredAbilityType` 1476).

Ce que le probe MESURE, etage par etage (jamais un scalaire ajuste) :

  1. **MONTAGE** -- la relique est-elle REELLEMENT montee ? Garde LUE dans `unitAbilityStates` :
     une entree `triggered` dont `raw[0] == 1476` et `raw[10] == 3` (hierarchie TERTIAIRE), avec le
     `level` demande. Les trois ecritures de #237 echouent DEUX FOIS EN SILENCE ; sans cette garde
     on mesurerait une unite SANS relique et l'accord serait vide de sens.
  2. **SEQUENCE DE PERCAGE** -- `combatSnapshot.units[].stats.extraPierce` du porteur apres CHAQUE
     attaque. C'est l'observable qui tranche les DEUX questions que le decompile seul ne ferme pas :
       * l'effet 1470 EMPILE-t-il (`k x extraPierceRatio`) ou est-il RAFRAICHI (constant) ? Le
         natif ne le dit que par le slot que `IdunBattle.Operations.AddEffectOperation$$
         UpdateExistingEffect` consulte, valeur runtime derriere la metadata IL2CPP -- donc une
         MESURE, pas une deduction ;
       * le seuil est-il `>= nrOfAttacks - 1` (reset a la N-ieme attaque, max
         `(N-1) x extraPierceRatio`) ou `>= nrOfAttacks` ? Un decalage d'UNE attaque, invisible de
         tout accord agrege.
  3. **RE-ARMEMENT DE L'ACTIVE** -- l'active du porteur (`EarlyWarningOverride` 1077) est CONSOMMEE
     AVANT la serie ; a l'attaque de reset elle doit redevenir `usable = true`. ⚠ **La difference
     avec `DaemonfleshPlate` est ICI** : `ResetActiveAbility` est DANS la branche THEN de l'unique
     classe native, donc le re-armement tombe DANS l'attaque, pas a la fin de phase.
     ⚠ L'active de Re'vas n'est PAS une attaque (elle somme des drones + Overwatch) : elle est donc
     castee HORS SERIE, dans `stage`, contrairement a `DaemonfleshPlate` dont le cast d'active EST
     une attaque et COMPTE dans le decompte. Si le cast est refuse, le canal ACTIVE n'est pas arme
     et le probe le DIT (jamais un vert qui ne mesure rien).
  4. **ACCORD PORT/NATIF** -- la meme sequence, rejouee OFFLINE par le vecteur du port
     (`finish_attack_triggers` = `On(9)`), depuis le `State` charge AVANT la premiere attaque. Pas
     de `phase_end_triggers` ici : cette relique n'a pas de volet `PhaseEnd`.
  5. **MUTANTS** -- six mutations du port, chacune avec son verdict ATTENDU. Un mutant qui ne mord
     pas nomme un temoin AVEUGLE ; c'est l'instrument, pas la decoration.

BRAS (`--bras`) :
  * `NOMINAL`    -- niveau 3 : `extraPierceRatio = 4`, `nrOfAttacks = 8`. Le niveau 3 est choisi
                    parce qu'il SEPARE le palier tertiaire du palier clampe : au dernier palier la
                    relique vaut `(6, 7)`, donc un port qui lirait le niveau PASSIF (50 sur tout
                    runner normalise) se trahirait sur les DEUX variables.
  * `NIVEAU6`    -- niveau 6 : `extraPierceRatio = 5`, `nrOfAttacks = 7`. Il discrimine le PALIER de
                    `nrOfAttacks` (8 -> 7 au 6e palier, la seule variable de la relique qui change
                    de palier) : il DEPLACE le reset, ce qu'aucun port au mauvais seuil ne
                    reproduit par hasard.
  * `SPECTATEUR` -- la relique reste sur `tauCrisis`, qui n'attaque PAS ; c'est une SECONDE unite de
                    mon camp (`tauDarkstrider`, SANS relique) qui frappe. Le gate
                    `get_OwnerIsCaster` doit FERMER le canal : le porteur ne doit gagner AUCUN
                    percage. Sans ce bras, le gate n'est exerce par AUCUN regime nominal (porteur ==
                    attaquant par construction).

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

ABILITY_ID = "Dw02AdvancedBurstCannon"
CARRIER = "tauCrisis"              # SEUL `allowedUnits` de la relique, HERO du pool rank 17
ATTACKER_ALT = "tauDarkstrider"    # bras SPECTATEUR : il frappe, il ne porte PAS la relique
TARGET = "astraBullgryn"           # cible-sac, PV forces
ACTIVE_OF_CARRIER = 1077           # `ActiveAbilityType.EarlyWarningOverride` -- l'active re-armee
EXTRA_PIERCE_KEY = "extraPierceRatio"   # `AbilityVariableType` 0x3f = 63
NR_OF_ATTACKS_KEY = "nrOfAttacks"       # `AbilityVariableType` 0x4e = 78
TRIGGERED_ID = 1476                # `TriggeredAbilityType.Dw02AdvancedBurstCannon`
HIERARCHY_TERTIARY = 3             # `UnitFactory$$AddConfiguredAbilities`, branche TERTIAIRE
#: cle de `combatSnapshot.units[].stats` pour `StatType.ExtraPierce` (0x1a) -- meme cle que
#: `UnitContext` lit (`entities/unit_context.py`).
PIERCE_STAT_KEY = "extraPierce"
#: Distance a laquelle la cible est placee. RANGED (`Pulse`, r2) et pas melee : cf. `stage`.
RANGED_DIST = 2


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


def garde_regime(level: int, p_pierce: list, p_atk: list) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage -- chacune ferme une porte de
    vert-qui-ne-mesure-rien.

      * niveau hors paliers -> `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au dernier
        palier et le bras NIVEAU ne discrimine plus rien ;
      * `nrOfAttacks <= 1` -> le seuil `>= N-1` vaudrait `>= 0`, VRAI des la premiere attaque : la
        branche ELSE ne serait JAMAIS prise et l'empilement serait inobservable ;
      * `extraPierceRatio <= 0` -> l'empilement n'aurait AUCUN observable sur `extraPierce`.
    """
    if not (1 <= level <= len(p_pierce)) or not (1 <= level <= len(p_atk)):
        raise SystemExit("niveau %d hors des paliers (%d/%d) : le clamp haut de "
                         "`TryGetVariableArrayForLevel` rendrait le bras NIVEAU non discriminant"
                         % (level, len(p_pierce), len(p_atk)))
    if p_atk[level - 1] <= 1:
        raise SystemExit("nrOfAttacks[%d] = %d : le seuil `>= N-1` serait VRAI des la 1re attaque, "
                         "la branche ELSE (l'empilement) ne serait jamais prise"
                         % (level, p_atk[level - 1]))
    if p_pierce[level - 1] <= 0:
        raise SystemExit("extraPierceRatio[%d] = %d : aucun observable sur extraPierce"
                         % (level, p_pierce[level - 1]))


def attaquant_de(bras: str) -> str:
    """Qui FRAPPE. Dans le bras SPECTATEUR ce n'est PAS le porteur -- c'est tout l'objet du bras."""
    return ATTACKER_ALT if bras == "SPECTATEUR" else CARRIER


def p_units_de(bras: str) -> str:
    return "%s,%s" % (CARRIER, ATTACKER_ALT) if bras == "SPECTATEUR" else CARRIER


def flags_de_build(bras: str, level: int) -> list:
    """FOYER UNIQUE des flags de montage, partage par le probe et par son cliquet
    (`tests/engine/runner/test_1012_dw02_burst_cannon_live.py`) : un montage DUPLIQUE derive de son
    original sans que rien ne le signale.

    ⚠ `--hp-player`/`--hp-target` font durer la bataille assez longtemps pour jouer les
    `nrOfAttacks + 2` actions de la serie. Contrairement a #916 (armure), ils ne << remettent pas a
    zero >> l'observable : `extraPierce` est une stat que RIEN d'autre ne pose sur `tauCrisis` (ni le
    kit, ni le profil d'arme, dont le `PiercingRatio` vit ailleurs) -- c'est verifie a la mesure, le
    premier releve de la serie est compare a `extraPierceRatio` et non a un socle suppose.

    ⚠ **MONTER LES PV NE SAUVE PAS LA SERIE, ET C'EST MESURE.** En MELEE, Re'vas tue la cible a la
    6e action quelle que soit sa sante : `900000` PV -> `189 389` de degat par action ; `9000000` PV
    -> `1 809 389`. Les deux points donnent `degat = 0,20 x maxHP + 9 389` -- une composante en
    POURCENTAGE des PV MAX (l'arme de melee de Re'vas est `Flame` + trait `OnFire`), donc **5
    actions pour tuer, a n'importe quel niveau de PV**. C'est pourquoi la serie se joue A DISTANCE
    (cf. `stage`) : son arme `Pulse` (r2) n'a aucun trait, et le degat retombe a ~8 500 par action --
    dix actions tiennent alors largement dans `900000`.

    ⚠ `--crit 0,0` / `--block-target 0,0` : un CRIT ou un BLOCK ne changent rien au compteur (le
    behaviour ne lit ni l'un ni l'autre), mais ils peuvent TUER la cible-sac et interrompre la
    serie."""
    return ["--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            "--hp-target", "900000", "--hp-player", "900000", "--no-ai",
            "--crit", "0,0", "--block-target", "0,0"]


def build(a, bras: str, level: int):
    """Un runner par bras, dispose aussitot (le budget est partage)."""
    fd, sf = tempfile.mkstemp(prefix="probe_1012_%s_l%d_" % (bras, level), suffix=".json")
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
        << pas de relique >>)."""
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
    """Amene la geometrie (attaquant AU CONTACT de la cible), verifie le MONTAGE de la relique,
    CONSOMME l'active du porteur, puis fige le snapshot de depart. On DEPLACE les unites -- jamais
    << bloque par la geometrie de spawn >>.

    ⚠ L'ORDRE EST LOAD-BEARING : le cast de l'active est fait AVANT le snapshot, donc l'etat
    << active consommee >> est DANS l'etat de depart des deux cotes (natif et port). C'est ce que
    `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` exige pour que
    `ResetActiveAbility` fasse quoi que ce soit -- sans cette consommation le volet RESET serait un
    vert vide.

    Rend `active_armee = False` si le cast a ete refuse : le canal ACTIVE n'est alors PAS mesure, et
    le probe le dit."""
    import hexgeo
    dv = h.dview()
    att_vis = attaquant_de(bras)
    att = h.by_visual(att_vis, dv)
    if att is None:
        raise MontageError("attaquant %s absent du decisionView" % att_vis)
    h.mine = att.get("owner")
    dv = h.my_turn()
    if dv is None:
        raise MontageError("le tour de l'attaquant est inatteignable")
    att = h.by_visual(att_vis, dv)
    tgt = h.by_visual(TARGET, dv)
    porteur = h.by_visual(CARRIER, dv)
    if att is None or tgt is None or porteur is None:
        raise MontageError("attaquant / cible / porteur absent du decisionView")

    raw = h.tertiary_raw(porteur["id"])
    if raw is None:
        raise MontageError("canal `unitAbilityStates.triggered` MUET pour le porteur -- "
                           "aucune mesure possible (tri-etat)")
    if raw == () or raw[0] != TRIGGERED_ID or raw[2] != HIERARCHY_TERTIARY or raw[1] != level:
        raise MontageError("relique NON montee comme attendu sur %s : lu %r, attendu "
                           "(%d, %d, %d) -- les trois ecritures de #237 echouent DEUX FOIS "
                           "EN SILENCE" % (CARRIER, raw, TRIGGERED_ID, level, HIERARCHY_TERTIARY))
    if bras == "SPECTATEUR":
        # CONTROLE NEGATIF : l'ATTAQUANT ne doit PAS porter la relique, sinon le gate qu'on croit
        # exercer serait satisfait par lui-meme et le bras ne mesurerait rien.
        r2 = h.tertiary_raw(att["id"])
        if r2 is None:
            raise MontageError("canal muet pour l'attaquant -- controle negatif impossible")
        if r2 != ():
            raise MontageError("l'ATTAQUANT porte lui aussi la relique (%r) : le bras SPECTATEUR "
                               "ne mesurerait rien" % (r2,))

    # cible A PORTEE RANGED de l'attaquant (distance 2 exactement).
    # ⚠ CE N'EST PAS UN CONFORT DE GEOMETRIE, c'est ce qui rend la serie JOUABLE, et c'est MESURE :
    # au CONTACT, l'arme de melee de Re'vas est `Flame` + trait `OnFire`, dont la composante en
    # POURCENTAGE des PV MAX (`0,20 x maxHP` -- deux points, 900k et 9M, cf. `flags_de_build`) tue la
    # cible a la 6e action QUELS QUE SOIENT ses PV. A distance 2 son arme est `Pulse` (r2, aucun
    # trait) : ~8 500 de degat par action, donc les `nrOfAttacks + 2` actions tiennent. Le behaviour
    # de la relique ne lit NI la nature du coup NI le profil (aucun `IsMeleeAttack` dans son
    # `CreateTrigger`), donc ce choix ne change AUCUN etage de la mecanique mesuree.
    apos = _pos(att)
    occupied = {_pos(u) for u in h.alive() if u.get("id") != tgt["id"]}
    cands = [h.board.coord(t) for t in sorted(h.board.by_id)
             if h.board.walkable(t) and hexgeo.distance(tuple(apos), h.board.coord(t)) == RANGED_DIST
             and h.board.coord(t) not in occupied]
    if not cands:
        raise MontageError("aucune tuile libre a distance %d de l'attaquant" % RANGED_DIST)
    if not h.place(tgt["id"], cands[0]):
        raise MontageError("le placement de la cible a echoue")
    na = h.normal_attack_type(att["id"])
    if na is None:
        raise MontageError("attaque normale introuvable pour l'attaquant")

    # CONSOMMATION de l'active du porteur (hors serie -- elle n'est pas une attaque).
    st0 = h.ability_state(porteur["id"], ACTIVE_OF_CARRIER)
    active_armee = False
    if st0 is not None and st0.get("usable"):
        if h.my_turn() is not None:
            h.cast(porteur["id"], tgt["id"], ACTIVE_OF_CARRIER)
            st1 = h.ability_state(porteur["id"], ACTIVE_OF_CARRIER)
            active_armee = bool(st1 is not None and st1.get("usable") is False)
        h.endturn()
    pierce0 = int(h.stats(porteur["id"]).get(PIERCE_STAT_KEY) or 0)
    return {"att": att["id"], "att_vis": att_vis, "tgt": tgt["id"], "porteur": porteur["id"],
            "na": na, "active_armee": active_armee, "pierce0": pierce0,
            "snapshot": h.snapshot()}


def attendus(bras: str, ep: int, nr: int, n: int, socle: int = 0, active_armee: bool = True):
    """Les DEUX sequences ATTENDUES, DERIVEES du RE -- foyer partage probe/cliquet.

    PERCAGE : `socle + k x extraPierceRatio` pour `k = 1..N-1`, puis `socle` a la N-ieme action (la
    branche THEN retire les N-1 piles d'un coup), puis le cycle REPART. Le maximum est donc
    `(N-1) x extraPierceRatio`, PAS `N x extraPierceRatio` -- c'est le
    `Subtract(ConfigVar(nrOfAttacks), <DSLFormulas+0x20> = Direct(1))` du seuil.
    `socle` = l'`extraPierce` du porteur AVANT la serie (mesure, pas suppose ; il vaut 0 sur ce
    porteur, et l'ecrire ainsi evite de confondre << 0 >> avec << non mesure >>).

    ACTIVE : consommee dans `stage`, elle redevient utilisable EXACTEMENT a la N-ieme action (celle
    qui prend la branche THEN) et le reste. ⚠ Contrairement a `DaemonfleshPlate`, le re-armement est
    IMMEDIAT : il n'y a ni marqueur ni `On(0x3a = PhaseEnd)`.

    Bras SPECTATEUR : le gate `get_OwnerIsCaster` ferme le canal -> percage CONSTANT au socle, ET
    active JAMAIS re-armee (le compteur du porteur ne monte pas, donc la branche THEN n'est jamais
    prise). Ce second canal est un observable A PART ENTIERE du bras : le percage seul ne dirait rien
    d'un port qui aurait perdu le gate SUR LA SEULE FEUILLE `ResetActiveAbility`.

    `active_armee = False` (le cast de l'active a ete refuse) -> le canal ACTIVE n'est pas mesure et
    l'attendu est `None`, jamais une sequence fabriquee."""
    if not active_armee:
        active = None
    elif bras == "SPECTATEUR":
        active = [False] * n
    else:
        active = [False] * (nr - 1) + [True] * (n - nr + 1)
    if bras == "SPECTATEUR":
        return [socle] * n, active
    pierce = ([socle + ep * k for k in range(1, nr)] + [socle]
              + [socle + ep * k for k in range(1, n - nr + 1)])
    return pierce, active


def serie_live(h, rec, n: int):
    """`n` attaques NORMALES de l'attaquant sur la cible. Rend `(percages, usables)` du PORTEUR.

    ⚠ Aucune action d'ability dans la serie : l'active de Re'vas (`EarlyWarningOverride`) n'est PAS
    une attaque, donc elle n'emet pas `On(9 = Attack)` et ne compte pas. C'est l'ECART avec #916, ou
    l'active du porteur EST offensive et OUVRE la serie."""
    percages, usables = [], []
    for i in range(n):
        if h.my_turn() is None:
            raise MontageError("tour inatteignable en cours de serie")
        a0 = h.cast(rec["att"], rec["tgt"], rec["na"])
        if not a0.get("ok"):
            raise MontageError("action %d (attaque normale) REFUSEE : %s"
                               % (i + 1, json.dumps(a0)[:300]))
        percages.append(int(h.stats(rec["porteur"]).get(PIERCE_STAT_KEY) or 0))
        st = h.ability_state(rec["porteur"], ACTIVE_OF_CARRIER)
        usables.append(None if st is None else bool(st.get("usable")))
        h.endturn()
    return percages, usables


# ------------------------------------------------------------------ rejeu OFFLINE (le port)

def serie_offline(board, rec, n: int, mutant: str = None):
    """Rejoue la MEME serie par le VECTEUR du port -- `On(9)`, c'est-a-dire ce que `Runner.apply`
    enchaine pour une attaque (`finish_attack_triggers` a la sortie d'`AttackDamageOperation`).

    Le degat n'est PAS rejoue : il n'entre dans AUCUN etage de cette mecanique (le behaviour ne lit
    ni PV ni profil). Rejouer le pipeline complet ajouterait du bruit sans rien mesurer de plus.

    Pas de `phase_end_triggers` : cette relique n'a pas de volet `PhaseEnd` (le re-armement est DANS
    la branche THEN). En ajouter un ferait croire a un accord qui viendrait d'ailleurs.

    L'etat << active consommee >> vient du SNAPSHOT (le cast est fait dans `stage`, AVANT). On le
    FORCE quand meme quand il n'a pas ete arme : sans lui,
    `BattleQuery$$EntityCanHaveActiveAbilityReset` rend FAUX et le volet RESET serait un vert vide.

    Rend `(percages, usables)` -- deux canaux d'observation distincts."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, ActiveAbilitiesComponent
    from engine.runner.operations.triggers.dispatch.attack import finish_attack_triggers
    from engine.entities.stats import StatType
    s = rec["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    if rec.get("active_armee"):
        e0 = st.get_entity(rec["porteur"])
        comp = e0.get_component(ActiveAbilitiesComponent) if e0 is not None else None
        for ab in (comp.abilities if comp is not None else ()):
            ab.can_still_be_used = False
    undo = _mute(mutant, st) if mutant else None
    try:
        percages, usables = [], []
        for _ in range(n):
            # `ranged=True` : la serie se joue A DISTANCE (cf. `stage`). Le `CreateTrigger` de la
            # relique ne porte AUCUN gate de nature de coup, donc cette valeur n'entre dans aucun
            # etage -- on la passe juste, comme le vecteur natif la porte.
            finish_attack_triggers(st, rec["att"], rec["tgt"], ranged=True)
            e = st.get_entity(rec["porteur"])
            sc = e.get_component(StatsComponent) if e is not None else None
            percages.append(int(sc.ctx.stat(StatType.EXTRA_PIERCE) or 0) if sc is not None else 0)
            comp = e.get_component(ActiveAbilitiesComponent) if e is not None else None
            usables.append(None if comp is None
                           else all(bool(ab.can_still_be_used) for ab in comp.abilities))
        return percages, usables
    finally:
        if undo is not None:
            undo()


def _mute(nom: str, st):
    """Installe une MUTATION du port et rend le callable qui la retire. Chaque mutant a un verdict
    ATTENDU (cf. `mutants_pour`) ; un mutant qui NE MORD PAS nomme un temoin aveugle."""
    import engine.runner.operations.triggers.loki.dw02_advanced_burst_cannon as DW
    from engine.entities.effects.loki.dw02_advanced_burst_cannon import (
        Dw02AdvancedBurstCannonExtraPierceRatioEffect as EFF)
    from engine.entities.behaviours import If, op_and
    from engine.entities.triggers import AmountIsEqualOrGreater
    from engine.entities.formulas import Difference, GetPersistentData
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import Owner
    from engine.entities.selectors.tiles import Caster
    from engine.entities.stats import StatType
    from engine.entities.effect_type import EffectType
    from engine.runner.abilities.behaviours.ability_state import ResetActiveAbility
    from engine.runner.abilities.behaviours.effects import (AddStaticStatModifierEffect,
                                                            RemoveEffect)
    from engine.runner.abilities.behaviours.persistent_data import (AddPersistentData,
                                                                    ClearPersistentData)
    orig_tree = DW.dw02_advanced_burst_cannon_tree
    orig_state = DW.triggered_ability_state
    orig_matches = DW.Dw02AdvancedBurstCannonAbility.matches
    orig_stack = EFF.stacks_stat_mod_on_add

    def _arbre(ep, nr, seuil_delta=1, increment=1, avec_clear=True, avec_reset=True):
        counter = GetPersistentData(DW.DW02_ADVANCED_BURST_CANNON, Owner(), DW._COUNTER_KEY)
        cond = AmountIsEqualOrGreater(counter, Difference(Const(int(nr)), Const(int(seuil_delta))))
        then_ = RemoveEffect(DW.EXTRA_PIERCE_EFFECT, Owner())
        if avec_reset:
            then_ = op_and(then_, ResetActiveAbility(Owner(), ignore_turn_flag=True))
        if avec_clear:
            then_ = op_and(then_, ClearPersistentData(DW.DW02_ADVANCED_BURST_CANNON, Owner(),
                                                     DW._COUNTER_KEY))
        else_ = op_and(
            AddStaticStatModifierEffect(
                Caster(), DW.EXTRA_PIERCE_EFFECT, int(StatType.EXTRA_PIERCE), int(ep),
                name=EffectType.Dw02AdvancedBurstCannon_ExtraPierceRatio.name),
            AddPersistentData(DW.DW02_ADVANCED_BURST_CANNON, Owner(), DW._COUNTER_KEY,
                              int(increment)))
        return If(cond, then_, else_)

    if nom == "SEUIL_N":            # `>= N` au lieu de `>= N - 1`
        DW.dw02_advanced_burst_cannon_tree = lambda ep, nr: _arbre(ep, nr, seuil_delta=0)
    elif nom == "NOCLEAR":          # la branche THEN ne vide plus le compteur
        DW.dw02_advanced_burst_cannon_tree = lambda ep, nr: _arbre(ep, nr, avec_clear=False)
    elif nom == "INCREMENT_2":      # `AddPersistentData(2)` au lieu de `<DSLFormulas+0x20> = Direct(1)`
        DW.dw02_advanced_burst_cannon_tree = lambda ep, nr: _arbre(ep, nr, increment=2)
    elif nom == "NORESET":          # la branche THEN ne re-arme plus l'active
        DW.dw02_advanced_burst_cannon_tree = lambda ep, nr: _arbre(ep, nr, avec_reset=False)
    elif nom == "NOSTACK":          # l'effet 1470 n'empile plus (gate << deja-present >> retabli)
        EFF.stacks_stat_mod_on_add = False
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
        DW.triggered_ability_state = _passif
    elif nom == "OWNERISCASTER_OFF":   # le gate `get_OwnerIsCaster` est neutralise
        DW.Dw02AdvancedBurstCannonAbility.matches = lambda self, state, ev: True
    else:
        raise SystemExit("mutant inconnu : %s" % nom)

    def undo():
        DW.dw02_advanced_burst_cannon_tree = orig_tree
        DW.triggered_ability_state = orig_state
        DW.Dw02AdvancedBurstCannonAbility.matches = orig_matches
        EFF.stacks_stat_mod_on_add = orig_stack
    return undo


def mutants_pour(bras: str, level: int, p_pierce: list, p_atk: list, active_armee: bool = True):
    """`(mutant, mord sur le canal PERCAGE ?, mord sur le canal ACTIVE ?)`. Chaque attente est
    DERIVEE de la structure de l'arbre, jamais du resultat observe :

      * `SEUIL_N` (`>= N` au lieu de `>= N-1`) DECALE le reset d'une action -> les DEUX canaux ;
      * `NOCLEAR` : le compteur reste `>= N-1` pour toujours -> la branche THEN est prise a CHAQUE
        action a partir de la N-ieme. Le PERCAGE ne repart donc jamais (il reste au socle), mais
        l'ACTIVE est re-armee a la N-ieme *et le reste* -- exactement la sequence nominale : ce
        canal-la ne peut PAS distinguer, et le dire est le point du mutant ;
      * `INCREMENT_2` : le compteur monte deux fois plus vite -> reset premature, les DEUX canaux ;
      * `NORESET` : ne touche que le volet ACTIVE ;
      * `NOSTACK` : seule la MAGNITUDE plafonne (le compteur, lui, est intact) -> le reset reste a
        la N-ieme action, canal ACTIVE inchange ;
      * `NIVEAU_PASSIF` : le niveau passif d'un runner normalise est 50, que
        `TryGetVariableArrayForLevel` CLAMPE au DERNIER palier. Son effet est donc **DERIVE, pas
        constant** : il ne deplace le reset que si `nrOfAttacks[niveau] != nrOfAttacks[-1]`, et il
        ne change la magnitude que si `extraPierceRatio[niveau] != extraPierceRatio[-1]`. L'ecrire
        en dur ferait rougir un bras sur une DEGENERESCENCE du gameconfig, pas sur un defaut du
        port ;
      * `OWNERISCASTER_OFF` : dans les bras nominaux porteur == attaquant, le gate est deja VRAI ->
        aucun canal (CONTROLE NEGATIF). C'est le bras SPECTATEUR qui l'exerce vraiment.

    `active_armee = False` (le cast de l'active a ete refuse) -> le canal ACTIVE n'est pas mesure,
    donc AUCUN mutant ne peut y mordre : les attentes de ce canal sont rabattues a False, et le
    probe l'annonce."""
    if bras == "SPECTATEUR":
        # ⚠ Le canal ACTIVE MORD ici, et c'est DERIVE : le porteur a bien consomme son active dans
        # `stage`, donc en neutralisant `get_OwnerIsCaster` son compteur monte sur les attaques du
        # TIERS et la branche THEN finit par re-armer l'active. C'est l'inverse de #916, dont le bras
        # SPECTATEUR n'arme PAS ce canal (son cast d'active EST une attaque, donc il ne peut pas etre
        # joue hors serie).
        return [("OWNERISCASTER_OFF", True, bool(active_armee))]
    passif_deplace_le_reset = (p_atk[level - 1] != p_atk[-1])
    passif_change_la_magnitude = (p_pierce[level - 1] != p_pierce[-1])
    table = [("SEUIL_N", True, True), ("NOCLEAR", True, False), ("INCREMENT_2", True, True),
             ("NORESET", False, True), ("NOSTACK", True, False),
             ("NIVEAU_PASSIF", passif_change_la_magnitude or passif_deplace_le_reset,
              passif_deplace_le_reset),
             ("OWNERISCASTER_OFF", False, False)]
    if active_armee:
        return table
    return [(nom, a, False) for nom, a, _ in table]


def run_bras(a, rpc, Board, bras: str, level: int, p_pierce: list, p_atk: list) -> int:
    rid, sf = build(a, bras, level)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    ep, nr = p_pierce[level - 1], p_atk[level - 1]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Live(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        try:
            rec = stage(h, bras, level)
        except MontageError as e:
            print("[%s/l%d] REFUS : %s" % (bras, level, e))
            return 2
        n = nr + 2                      # deux actions APRES le reset -> le cycle doit REPARTIR
        try:
            percages, usables = serie_live(h, rec, n)
        except MontageError as e:
            print("[%s/l%d] REFUS : %s" % (bras, level, e))
            return 2

        att_p, att_us = attendus(bras, ep, nr, n, socle=rec["pierce0"],
                                 active_armee=rec["active_armee"])
        off_p, off_u = serie_offline(h.board, rec, n)
        accord = (off_p == percages)
        conforme = (percages == att_p)
        rc = 0 if (accord and conforme) else 1
        print("[%s/l%d] extraPierceRatio=%d nrOfAttacks=%d socle=%d active_armee=%s"
              % (bras, level, ep, nr, rec["pierce0"], rec["active_armee"]))
        print("   percage natif  : %s" % percages)
        print("   percage port   : %s   accord=%s" % (off_p, accord))
        print("   percage attendu: %s   conforme=%s" % (att_p, conforme))

        if att_us is not None:
            ok_live = (usables == att_us)
            ok_port = (off_u == att_us)
            rc |= 0 if (ok_live and ok_port) else 1
            print("   active natif  : %s   conforme=%s" % (usables, ok_live))
            print("   active port   : %s   conforme=%s" % (off_u, ok_port))
        else:
            print("   active : CANAL NON ARME (le cast de %d a ete refuse ou l'active etait deja "
                  "consommee) -- ce volet n'est PAS mesure dans ce bras" % ACTIVE_OF_CARRIER)

        for nom, mord_p, mord_u in mutants_pour(bras, level, p_pierce, p_atk,
                                                active_armee=rec["active_armee"]):
            m_p, m_u = serie_offline(h.board, rec, n, mutant=nom)
            got_p, got_u = (m_p != off_p), (m_u != off_u)
            if got_p != mord_p or got_u != mord_u:
                rc |= 1
            print("   mutant %-18s percage=%-5s (att %-5s) active=%-5s (att %-5s)  %s"
                  % (nom, got_p, mord_p, got_u, mord_u, m_p))
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

    p_pierce, p_atk = paliers(EXTRA_PIERCE_KEY), paliers(NR_OF_ATTACKS_KEY)
    print("== #1012 %s -- porteur %s, cible %s" % (ABILITY_ID, CARRIER, TARGET))
    print("   paliers extraPierceRatio : %s" % p_pierce)
    print("   paliers nrOfAttacks      : %s" % p_atk)
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
        level = 6 if bras == "NIVEAU6" else 3
        garde_regime(level, p_pierce, p_atk)
        rc |= run_bras(a, rpc, Board, bras, level, p_pierce, p_atk)
    print("== rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
