"""#570 -- `1057 GrotTank` (`orksBigMek`) : la face COMBAT, etage par etage.

Artefact natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.GrotTankAbility$$ExecuteBehaviour`
(DECOMPILE, mirror 1:1 -- l'arbre vit dans `engine/runner/abilities/orks.py::grot_tank_tree`).
L'ability etait un NO-OP SILENCIEUX avant cette tranche (absente d'`ABILITY_CLASSES`, donc ignoree
par `AbilityHandler.visit_ActiveAbilityMessage` -- 0 summon, 0 degat, aucune erreur).

LA CATEGORIE D'AUDIT DISAIT "SUMMON", ET C'EST VRAI -- MAIS CA N'EN DIT QU'UN CINQUIEME. Le
behaviour n'a qu'UN `AActiveAbility.Execute`, et il compose CINQ mecaniques dans les options de
spawn : (1) le `Spawn(Caster@0x48, Target@0x60, unitId, opts)` tile-target ; (2)
`WithStatsFromConfig` (stats du summon depuis le gameconfig) ; (3) `abilitiesLevel =
AbilityLevelAmount(Owner@0x30, <ce type>)` ; (4) `opts+0x28 = [StatModifierFormula(Health, Initial,
TankHealth(), null)]` -- un OVERRIDE DE PV PAR FORMULE, qui n'avait AUCUN mirror ; (5) `opts+0x18 =
PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` -- le tank tire des son apparition, sans
bouger. Un critere unique ("un summon est apparu") serait VERT sur un port qui oublierait (4) et
(5) : ce fichier les garde SEPAREMENT.

CE QUE CHAQUE TEST TIENT, ET LA MUTATION QUI LE REND ROUGE :

  * `test_grot_tank_spawns_on_the_targeted_tile` -- le `Spawn` pose UNE unite, sur la tuile CIBLEE
    (et pas ailleurs : le tile-selecteur natif est `Target@0x60` BRUT, aucun `CanAddUnit`, aucun
    `AdjacentTiles`). Mutation vue rouge : rendre la liste de tuiles vide dans la feuille `Spawn`.
  * `test_grot_tank_health_follows_rounds_started` -- LE test discriminant, et le seul qui voie
    l'etage NEUF. `TankHealth = summonHp + RoundsStarted(Caster) x extraHp`. Le test attend
    plusieurs tours AVANT de caster, pour que `turnsStarted(caster) >= 2` : les trois hypotheses
    concurrentes (`summonHp` seul / `summonHp + 1 x extraHp` / la formule complete) deviennent alors
    TROIS valeurs distinctes, et le test les separe explicitement. Au tour 1 elles n'en font que
    deux -- c'est pourquoi l'attente n'est pas une precaution mais le montage.
  * `test_grot_tank_onappearance_damage_bit_exact` -- le cran QUANTITATIF de (5) : le TOTAL de
    degat par CIBLE doit coincider bit-a-bit. Un critere "des degats ont eu lieu" serait satisfait
    par n'importe quel pipeline. Le montage RAPPROCHE le Big Mek d'un ennemi (`--place`/`--a-place`)
    : aux spawn points de `MC1_67` le tank apparait a 7 hex de la melee, donc HORS de sa portee (3),
    et l'etage resterait INERTE des deux cotes -- un vert qui ne mesure rien.
  * `test_grot_tank_summon_is_not_activatable` -- #291 : `TriggerSpawnedUnitBehaviours` ->
    `FinishUnitTurn(spawned, isTerminated: true)`. Le tank n'entre PAS dans `decisionView.
    toActivate`. C'est la REPONSE CORRECTE du natif ("The Grot Tank cannot move in its first turn"),
    pas un trou de harnais -- on la fige pour qu'un futur port ne la "repare" pas.

MESURE (2026-08-08, board MC1_67, seed 777, `orksBigMek` rank 17 -> niveau 50, multiplicateur
180 %) : `summonHp = 6980`, `extraHp = 997`. A `turnsStarted = 1` le natif pose un tank a
**7977** PV (= 6980 + 1 x 997) ; a `turnsStarted = 4`, **10968** (= 6980 + 4 x 997). Le port rend
les memes deux valeurs. Degat on-appearance sur `orksNob` : **1522** des deux cotes. Sortie brute :
`probe_570_grot_tank.py`.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatType
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.components import HealthComponent, PositionComponent, StatsComponent
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

#: Perimetre qui doit RE-JOUER ce fichier (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` (semantique pytest,
        # jamais importee) porte `green_skip_guard` (#455) et les fixtures `autouse` + de montage
        # (`host`/`live_session`) dont le verdict de CHAQUE test de ce fichier depend.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE et non feuille a feuille : charger une ability tire le
        # registre, tout le vocabulaire DSL, les Operations, l'IA et le pathfinding -- une liste
        # choisie serait un faux vert, elle ne pourrait pas montrer le module qu'elle a oublie.
        # Foyers VRAIMENT load-bearing, pour la relecture humaine :
        # `abilities/orks.py` (l'arbre `grot_tank_tree` et la formule `grot_tank_health_formula`),
        # `handler.py` + `attack_type.py` + `targeting.py` (les trois registres, dont le CONTRAT DE
        # DISJONCTION du masque), `abilities/behaviours/summon.py` (la feuille `Spawn`, le mirror
        # `StatModifierFormula` et `get_stats_to_override`), `operations/spawn.py`
        # (`_spawn_config_grot` + `apply_spawn_stat_overrides`, le foyer de l'override de PV, et
        # `trigger_spawned_unit_finish_turn` que le test #291 mesure), `abilities/loki/summon.py`
        # (le corps unique de `PerformAIAbilityUnitBehaviour`, dont le degat est confronte
        # BIT-EXACT), `entities/formulas.py` (`Sum`/`Multiply`/`RoundsStarted`, les trois noeuds de
        # `TankHealth`), `entities/stats.py` (`StatPart.INITIAL` = l'ECRASEMENT lu dans
        # `FillUpStatComponent$$ApplyModifier` case 3).
        "scripts/python/engine/**/*.py",
        # Modules de la RACINE : la cascade des `conftest.py` de `tests/engine/runner` importe une
        # vingtaine de probes plus `hexgeo` / `engine_validate` / `rl_duel`. Ils entrent dans la
        # fermeture de CE fichier, qu'il les cite ou non -- et `rl_duel build --place` EST le
        # montage du test on-appearance : sans lui le tank spawne hors de sa portee.
        "scripts/python/*.py",
        # Le KIT : `constants.unitId` = `orksGrotTank`, et les `summonHp`/`extraHp`/`summonDmg`/
        # `summonArmor` de la config 1057 -- un re-dump qui les bouge change les PV mesures ici.
        "data/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "L'arbre DSL de 1057 et ses CINQ etages, les trois registres que ce fichier "
              "confronte (ABILITY_CLASSES / TARGETING_OPTIONS / ABILITY_ATTACK_TYPE), le mirror "
              "NEUF `StatModifierFormula` + `SpawnUnitBehaviour$$GetStatsToOverride` (volet "
              "formule) et son application `StatPart.Initial` dans `_spawn_config_grot`, le corps "
              "unique de `PerformAIAbilityUnitBehaviour` dont le degat est confronte BIT-EXACT, le "
              "gate #291 `FinishUnitTurn(spawned)`, et le kit gameconfig d'ou sortent summonHp / "
              "extraHp. `build: True` parce que les quatre etages se confrontent au natif par RPC : "
              "un changement de build change le decompile dont ce port est le mirror, et les "
              "valeurs de PV mesurees (7977 / 10968) sortent de la config du build courant.",
}

AGENT_ID = "a4ccf48ef8cb02117"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
# `data/` = ce qu'on LIT (VERSIONNE), `logs/` = ce qu'on ECRIT (gitignore) -- cf. CLAUDE.md.
STATE = ROOT / "logs" / f"_pytest_grottank_{AGENT_ID}.json"        # state-file UNIQUE

GROT_TANK = int(ActiveAbilityType.GrotTank)                        # 1057
ABILITY_ID = "GrotTank"
CARRIER = "orksBigMek"
ENEMIES = "orksNob,orksRuntherd,tyranWingedPrime"
SEED = "777"
BOARD = "MC1_67"

# Positions CRAFTEES : le Big Mek AU CONTACT d'un ennemi. Sans elles, les spawn points de MC1_67
# laissent 7 hex entre les deux camps -> le tank pose apparait hors de sa portee (3) et l'etage
# on-appearance reste inerte DES DEUX COTES (un vert qui ne mesure rien).
CASTER_POS = (4, 5)
ENEMY_POS = (5, 5)


@pytest.fixture(scope="module")
def grot(host, live_session):
    """Fabrique de runners ISOLES (Big Mek + 3 ennemis, positions craftees), disposes au teardown."""
    created: list[int] = []

    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    def _build():
        STATE.parent.mkdir(parents=True, exist_ok=True)
        if STATE.exists():
            STATE.unlink()
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
             "--p-units", CARRIER, "--a-units", ENEMIES,
             "--place", "%s:%d,%d" % (CARRIER, CASTER_POS[0], CASTER_POS[1]),
             "--a-place", "orksNob:%d,%d" % ENEMY_POS,
             "--state-file", str(STATE)],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not STATE.exists():
            pytest.skip(f"build {CARRIER} KO: {(proc.stderr or proc.stdout or '')[-300:]}")
        rid = json.loads(STATE.read_text())["runnerId"]
        created.append(rid)
        return rid

    yield _build, _rpc
    for rid in created:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


def _units(rpc, rid) -> list:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return list(ob.get("units") or [])


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state, board


def _caster_id(rpc, rid):
    u = next((x for x in _units(rpc, rid)
              if x.get("visualId") == CARRIER and not x.get("isDead")), None)
    if u is None:
        pytest.skip("caster absent")
    return u["squadId"]


def _legal_tile(rpc, rid, cid, wait_turns: int = 0, max_turns: int = 12):
    """La 1re tuile que le NATIF publie comme cible legale de 1057, apres `wait_turns` tours passes.

    `endturn` fait passer le tour SANS jouer l'IA -> les positions ne bougent pas, seul
    `turnsStarted` monte : c'est le levier qui rend l'etage PV discriminant sur la PENTE."""
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
    me = next((u.get("owner") for u in (dv0.get("units") or []) if u.get("id") == cid), None)
    waited = 0
    for _ in range(max_turns + 2 * wait_turns + 2):
        sn = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
        if sn.get("currentPlayer") != me:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        if waited < wait_turns:
            waited += 1
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "allAbilities": True}, 90) or {}
        for unit in (at.get("units") or []):
            if unit.get("unitId") != cid:
                continue
            for ab in (unit.get("abilities") or []):
                if ab.get("abilityId") != GROT_TANK:
                    continue
                for t in (ab.get("fromHere") or []):
                    tile = t.get("tile") or {}
                    if t.get("kind") == "tile" and tile.get("col") is not None:
                        return (tile["col"], tile["row"])
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    pytest.skip("le natif ne publie aucune tuile legale pour 1057")


def _port_run(rpc, rid, cid, tile_id):
    """Execute l'arbre PORTE sur l'etat AVANT -> (dict de retour, state, niveau, mult, turnsStarted)."""
    state, _b = _load(rpc, rid)
    cls = ABILITY_CLASSES.get(GROT_TANK)
    assert cls is not None, "1057 GrotTank absente d'ABILITY_CLASSES"
    ce = state.get_entity(cid)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    level = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100) if sc is not None else 100
    turns = int(sc.ctx.get_stat(int(StatType.TURNS_STARTED)) or 0) if sc is not None else 0
    out = cls().execute_behaviour(state, cid, tile_id) or {}
    return out, state, level, mult, turns


def _cast(rpc, rid, cid, tile):
    """Applique le cast NATIF sur `tile` = (col, row). Rend (units_avant, units_apres)."""
    before = _units(rpc, rid)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "abilityType": GROT_TANK,
        "to": {"col": tile[0], "row": tile[1]}}}, 90) or {}
    act = (res.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    return before, _units(rpc, rid)


# ------------------------------------------------------------------ E1 : le spawn, et SA tuile

def test_grot_tank_spawns_on_the_targeted_tile(grot):
    """`Spawn(Caster@0x48, Target@0x60, GetStringConstant(unitId), opts)` : UNE unite, sur la tuile
    CIBLEE. Le tile-selecteur natif est `Target` BRUT -- la contrainte "hex adjacent LIBRE" vient
    du masque (`TargetIsTile | TargetTileIsFree`, portee adjacente), pas de l'arbre."""
    build, rpc = grot
    rid = build()
    cid = _caster_id(rpc, rid)
    tile = _legal_tile(rpc, rid, cid)
    _state, board = _load(rpc, rid)
    port_out, port_state, _lvl, _m, _t = _port_run(rpc, rid, cid, board.id_at(*tile))
    before, after = _cast(rpc, rid, cid, tile)

    known = {u.get("squadId") for u in before}
    fresh = [u for u in after if u.get("squadId") not in known and not u.get("isDead")]
    nat_tiles = sorted((u.get("col"), u.get("row")) for u in fresh)
    port_pc = [port_state.get_entity(int(g)).get_component(PositionComponent)
               for g in (port_out.get("spawned") or [])]
    port_tiles = sorted((pc.col, pc.row) for pc in port_pc if pc is not None)
    print(f"\n[570/spawn] cible={tile} natif={nat_tiles} "
          f"({[u.get('visualId') for u in fresh]}) port={port_tiles}")
    assert nat_tiles == [tuple(tile)], \
        f"le natif spawne sur {nat_tiles}, attendu la seule tuile ciblee {[tuple(tile)]}"
    assert port_tiles == nat_tiles, f"le port spawne sur {port_tiles}, natif {nat_tiles}"


# ------------------------------------------------------------------ E2 : l'etage StatModifierFormula

def test_grot_tank_health_follows_rounds_started(grot):
    """LE test discriminant -- `StatModifierFormula(Health, Initial, TankHealth(), null)`.

    `TankHealth = Sum(Direct(summonHp), Multiply(RoundsStarted(Caster@0x48), Direct(extraHp)))`.
    Le montage attend plusieurs tours (`wait_turns`) AVANT de caster : a `turnsStarted >= 2` les
    trois hypotheses concurrentes deviennent TROIS valeurs distinctes --
      * `summonHp` seul                    = l'override oublie (le mode de panne le plus probable,
                                             puisque `WithStatsFromConfig` pose deja `summonHp`) ;
      * `summonHp + 1 x extraHp`           = un `RoundsStarted` fige a 1 ;
      * `summonHp + turnsStarted x extraHp`= la formule.
    Le test REFUSE les deux premieres explicitement, puis exige l'egalite natif == port.

    ⚠ Borne BASSE sur `turnsStarted` (`>= 2`), jamais une egalite : le nombre de tours reellement
    passes depend du gate de ciblage natif, et un `== N` rougirait sur un board plus lent."""
    build, rpc = grot
    rid = build()
    cid = _caster_id(rpc, rid)
    tile = _legal_tile(rpc, rid, cid, wait_turns=3)
    _state, board = _load(rpc, rid)
    port_out, port_state, level, mult, turns = _port_run(rpc, rid, cid, board.id_at(*tile))
    before, after = _cast(rpc, rid, cid, tile)

    v_hp = int(ability_var(ABILITY_ID, "summonHp", level, multiplier_pct=mult) or 0)
    v_extra = int(ability_var(ABILITY_ID, "extraHp", level, multiplier_pct=mult) or 0)
    known = {u.get("squadId") for u in before}
    fresh = [u for u in after if u.get("squadId") not in known and not u.get("isDead")]
    assert fresh, "aucun summon natif -> l'etage PV n'est pas mesurable"
    # `observeBattle` ne publie pas `maxHp` sur ce chemin ; l'unite VIENT d'apparaitre -> hp == max.
    nat_hp = int(fresh[0].get("hp"))
    port_hp = [
        port_state.get_entity(int(g)).get_component(HealthComponent).hp_max
        for g in (port_out.get("spawned") or [])]
    print(f"\n[570/hp] turnsStarted={turns} summonHp={v_hp} extraHp={v_extra} "
          f"natif={nat_hp} port={port_hp}")
    assert turns >= 2, \
        (f"turnsStarted={turns} : l'etage n'est PAS discriminant (les hypotheses coincident) -- "
         f"le montage `wait_turns` n'a pas mordu")
    assert v_extra > 0, "extraHp nul : la pente serait invisible"
    assert nat_hp != v_hp, \
        (f"le natif rend `summonHp` SEUL ({v_hp}) -> l'override `StatModifierFormula` ne mordrait "
         f"pas ; re-lire `GrotTankAbility$$TankHealth` avant de conclure")
    assert nat_hp != v_hp + v_extra, \
        f"le natif rend `summonHp + 1 x extraHp` ({v_hp + v_extra}) -> `RoundsStarted` fige a 1"
    assert nat_hp == v_hp + turns * v_extra, \
        (f"PV natif {nat_hp} != summonHp + turnsStarted x extraHp = "
         f"{v_hp} + {turns} x {v_extra} = {v_hp + turns * v_extra}")
    assert port_hp == [nat_hp], f"PV port {port_hp} != natif [{nat_hp}]"


# ------------------------------------------------------------------ E4 : l'on-appearance

def test_grot_tank_onappearance_damage_bit_exact(grot):
    """`opts+0x18 = PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` -- « can immediately
    attack an enemy in range » du tooltip i2. Cran QUANTITATIF : le TOTAL de degat par CIBLE doit
    coincider bit-a-bit, sinon le tank n'attaque pas la meme chose ou pas par le meme pipeline.

    L'assertion `nat_dmg` non vide est ce qui empeche un VERT VIDE : sans le placement crafte le
    tank apparait hors de sa portee, les deux cotes rendent `{}` et l'egalite serait satisfaite
    sans rien avoir mesure."""
    build, rpc = grot
    rid = build()
    cid = _caster_id(rpc, rid)
    tile = _legal_tile(rpc, rid, cid)
    _state, board = _load(rpc, rid)
    port_out, _ps, _l, _m, _t = _port_run(rpc, rid, cid, board.id_at(*tile))
    before, after = _cast(rpc, rid, cid, tile)

    hp0 = {u.get("squadId"): u.get("hp") for u in before}
    nat_dmg = {u.get("squadId"): hp0[u["squadId"]] - u.get("hp")
               for u in after
               if u.get("squadId") in hp0 and u.get("hp") != hp0[u.get("squadId")]}
    port_dmg: dict = {}
    for at in (port_out.get("attacks") or []):
        port_dmg[at["target"]] = port_dmg.get(at["target"], 0) + int(at.get("total") or 0)
    print(f"\n[570/onappear] degat natif={nat_dmg} port={port_dmg}")
    assert nat_dmg, \
        ("aucun degat on-appearance cote natif : le tank est hors de portee (montage `--place` "
         "casse) -- l'egalite serait un VERT VIDE")
    assert port_dmg == nat_dmg, \
        f"degat on-appearance port {port_dmg} != natif {nat_dmg}"


# ------------------------------------------------------------------ E5 : #291, le summon n'agit pas

def test_grot_tank_summon_is_not_activatable(grot):
    """#291 -- `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` termine le tour de toute unite
    qui apparait pendant le tour de son proprietaire (`FinishUnitTurn(spawned, isTerminated: true)`
    -> `MarkUnitAsNoActionAvailable`), sauf `Steppable`/`Hero`. Le Grot Tank n'est ni l'un ni
    l'autre (traits `Summon`/`Mechanical`/`BattleFatigue`/`Vehicle`), donc il n'entre PAS dans
    `decisionView.toActivate` : c'est « The Grot Tank cannot move in its first turn » du tooltip,
    et c'est la REPONSE CORRECTE du natif -- pas un trou a combler."""
    build, rpc = grot
    rid = build()
    cid = _caster_id(rpc, rid)
    tile = _legal_tile(rpc, rid, cid)
    before, after = _cast(rpc, rid, cid, tile)

    known = {u.get("squadId") for u in before}
    fresh = [u.get("squadId") for u in after if u.get("squadId") not in known
             and not u.get("isDead")]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
    to_activate = list(dv.get("toActivate") or [])
    print(f"\n[570/291] summons={fresh} toActivate={to_activate}")
    assert fresh, "aucun summon : le gate #291 n'est pas mesurable"
    assert not [i for i in fresh if i in to_activate], \
        (f"le summon {fresh} est dans toActivate {to_activate} -- `FinishUnitTurn(spawned, "
         f"isTerminated: true)` n'a pas ete applique")


# ------------------------------------------------------------------ D1 : la face DECISION

def test_grot_tank_playbook_utility_matches_native(grot):
    """DECIDER != EXECUTER -- ce test tient l'AUTRE face.

    `IdunBattle.AI.Playbook.Loki.GrotTankPlaybook$$GetUtility(caster, summonTile)` = le nombre
    d'unites NON AMIES dans le DISQUE de rayon **3** autour de la tuile de spawn (slots
    `IBattleQuery` 118 `GetSurroundingUnits` / 146 `AreFriends`) -- pas les adjacentes, pas toutes
    les unites. L'oracle est `ncEvaluate --sweep`, qui invoque la leaf native PAR POSITION du
    caster et decode `Bucket.best` ; le port recalcule le max de sa propre utilite sur les tuiles
    de spawn eligibles depuis cette meme position.

    Le rayon est ce que ce test tranche : sur le montage, les positions se ventilent en utilites
    **1 / 2 / 3** -- un rayon 1 ou 2 les ecraserait, un predicat "toutes les unites" les
    augmenterait. L'assertion sur la DISPERSION (au moins deux valeurs distinctes) est ce qui
    empeche un vert degenere ou toutes les positions vaudraient la meme chose."""
    build, rpc = grot
    rid = build()
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180) or {}
    cid = next((u.get("id") for u in (dv.get("units") or [])
                if u.get("visualId") == CARRIER and u.get("alive")), None)
    if cid is None:
        pytest.skip("caster absent")
    nc = rpc("ncEvaluate", {"runnerId": rid, "unitId": cid,
                            "abilityType": GROT_TANK, "sweep": True}, 180) or {}
    if not nc.get("ok"):
        pytest.skip(f"ncEvaluate indispo: {nc.get('error')}")
    assert nc.get("playbookClass") == "GrotTankPlaybook", \
        f"le natif charge {nc.get('playbookClass')} pour 1057, pas GrotTankPlaybook"
    rows = [r for r in (nc.get("positions") or []) if r.get("util") is not None]
    assert rows, ("bucket natif VIDE a toutes les positions -- le montage n'atteint pas le "
                  "regime (aucun ennemi a portee 3 d'aucune tuile de spawn)")

    import hexgeo
    from engine import battle_query as bq
    from engine.ai import context as ai_ctx
    from engine.playbook import noncomparable as playbooks
    from engine.playbook import scene as scene_mod
    from engine.playbook.noncomparable._base import eligible_target_tiles
    from engine import weights as W

    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    predictor = scene_mod.build_predictor(rpc, rid)
    ctx = ai_ctx.build(rpc, rid, dv, {u.get("unitId"): u for u in (mov.get("units") or [])},
                       cid, W.load(), predictor, debug=False)
    nc_ctx = playbooks.NCContext(
        uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
        enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos, walkable_by_pos=ctx.walkable_by_pos,
        plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
        elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets, wt=ctx.wt,
        is_temporary_by_pos=ctx.is_temporary_by_pos, effects_by_pos=ctx.effects_by_pos,
        obs_units=ctx.obs_units, tile_id_by_pos=ctx.tile_id_by_pos,
        active_levels=ctx.active_ability_levels, units=ctx.units,
        cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)
    pb = playbooks.PLAYBOOKS.get(GROT_TANK)
    assert pb is not None, "1057 absente du registre NonComparable"
    _fh, union = eligible_target_tiles(nc_ctx, GROT_TANK)
    neigh = bq.neigh_map(nc_ctx)
    mismatch = []
    natives = []
    for r in rows:
        p = r.get("pos")
        T = tuple(p) if isinstance(p, list) else p
        if not isinstance(T, tuple):
            continue
        mine = 0.0
        for st in union:
            if not bq.is_adjacent(T, st, nc_ctx.elev_by_pos, neigh):
                continue
            mine = max(mine, float(sum(1 for e in (ctx.epos or [])
                                       if hexgeo.distance(st, (e[0], e[1]))
                                       <= pb._UTILITY_RADIUS)))
        natives.append(float(r["util"]))
        if abs(float(r["util"]) - mine) >= 1e-6:
            mismatch.append((T, r["util"], mine))
    print(f"\n[570/nc] {len(natives)} positions ; utilites natives {sorted(set(natives))} ; "
          f"divergences={mismatch[:6]}")
    assert natives, "aucune position confrontee"
    assert len(set(natives)) >= 2, \
        (f"toutes les positions valent {set(natives)} -- regime DEGENERE : le rayon n'est pas "
         f"discrimine, re-crafter le montage")
    assert not mismatch, \
        f"utilite natif != port sur {len(mismatch)} position(s) : {mismatch[:6]}"
    cands = pb.generate_candidates(nc_ctx) or []
    assert cands, "le natif propose et le port ne propose RIEN"
    assert abs(float(cands[0]["pred"]) - max(natives)) < 1e-6, \
        f"argmax port {cands[0]['pred']} != max natif {max(natives)}"
