"""probe #302 tranche 3 -- `1148 DaemonicOrdnance` sur la route de decision a cibles TUILE.

CE QUE CE PROBE MESURE (et qu'aucune lecture du decompile ne donne)
-------------------------------------------------------------------
La RE est faite (`engine/playbook/daemonic_ordnance.py` porte le mirror 1:1 de
`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$CalculateCustomUtility`). Restent QUATRE
choses qui ne se lisent que LIVE :

1. **Le cooldown.** 1148 arrive avec `initialCooldownTurns = 1` : au tour du build elle est
   INDISPONIBLE, et une mesure faite la se lit comme « le natif refuse la cible tuile » -- c'est
   exactement l'artefact qui avait produit une conclusion architecturale FAUSSE sur 1169
   (`case-302` §5). `build_ready` PURGE le cooldown et l'assert.
2. **La DIRECTION du triangle.** `DaemonicOrdnanceAbility$$GetTargetAreaTiles` vaut
   `TilesOnSameElevation(target, TilesInTriangleShape(target, If(IsPositionMachineForCurrentPlayer(2),
   1, 4)), 1)`. Le predicat interroge le slot MoW du joueur COURANT -- une donnee d'ETAT. Le probe
   imprime `decisionView.mows` et le slot retenu : si le port et le natif divergent la-dessus, ils
   visent deux triangles DIFFERENTS, et le desaccord de cible le montre.
3. **L'accord natif/moteur sur (ability, cible TUILE)**, par `aiDryRunAllUnits` -- il n'existe
   aucun oracle PAR ETAGE pour une cible tuile (`rpc-predict.ts::pairUtility` ne resout `targetId`
   que sur `EntityType.Unit`, cf. `case-302` §7 tranche 5).
4. **Les bras de NECESSITE** : custom force a 0, registre non-attaque vide, domaine force a UNITE,
   `_best_attack`. Sans eux, un accord ne prouve pas que ce port-ci l'a produit.

MONTAGE. 1148 est portee par `blackForgefiend` (MACHINE OF WAR, hors `decisionView.units`) : on la
GREFFE sur une unite du pool -- le natif charge le playbook PAR ABILITY, jamais par unite
(`case-92` §5bis), et le custom de 1148 ne lit NI stat NI trait du caster (seulement `caster.team`,
pour `IsEnemy`), donc la greffe est legitime ici.

Les trois ennemis sont poses en TRIANGLE HEX SERRE (A, A+S, A+SE). Ce cluster donne du CONTRASTE
quelle que soit la direction retenue par le natif -- c'est voulu : le montage ne presuppose pas la
direction, il la laisse trancher le choix de tuile.

  * direction 1 (coin {S, SE}) : la tuile A capte les TROIS (custom 30) ;
  * direction 4 (coin {NW, N}) : la tuile A+S en capte DEUX (custom 20).

DEUX BRAS, et le second est le TEMOIN :
  * `--hp-target 400000` : cibles quasi increvables -> l'utilite d'attaque s'effondre, 1148 domine ;
  * `--hp-target 1`      : cibles one-shot -> le composite `KillUnit` domine, le natif ATTAQUE.
Sans le temoin, un port qui casterait 1148 SYSTEMATIQUEMENT passerait toutes les autres gardes.

Usage (depuis scripts/python, ASCII only) :
    python probe_302_3_daemonic_ordnance.py --decision
    python probe_302_3_daemonic_ordnance.py --stage        # etage kit/cooldown/domaine seul
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.selectors.geometry import neighbour_at

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_do_graft.json"

DAEMONIC = int(ActiveAbilityType.DaemonicOrdnance)          # 0x47c = 1148
DAEMONIC_ID = "DaemonicOrdnance"                            # cle gameconfig
NORMAL = 69

BOARD = "MC1_67"
# Plateau du SECOND CAS DISCRIMINANT (`--flip`) : son SpawnPointSet actif declare
# `MachineOfWarPosition = 0` pour les DEUX camps, la ou celui de `MC1_67` declare (2, 1). Le
# predicat `IsPositionMachineForCurrentPlayer(2)` bascule donc de VRAI a FAUX, et avec lui la
# direction du triangle (`{S, SE}` -> `{NW, N}`). Meme geometrie (7x9), memes tuiles jouables.
BOARD_FLAT = "C1_03"
SEED = 909
RANK = "17"

GRAFT_ON = "deathTyphus"                  # dans `rl_duel build --list-pool` au rank 17
P_UNITS = "deathTyphus,deathPutrifier"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = GRAFT_ON
A_VID, B_VID, C_VID = "orksWarboss", "necroWarden", "astraCreed"

CASTER_TILE = (2, 4)
CLUSTER_ANCHOR = (4, 4)
# Cluster TRIANGLE HEX SERRE : l'ancre + ses voisins S (dir 0) et SE (dir 1). Cf. l'en-tete --
# `_TRIANGLE_SHAPE_DIRECTIONS` de `engine.entities.selectors.geometry` : coin 1 = {S, SE},
# coin 4 = {NW, N}. Ce cluster porte du contraste dans les DEUX cas.
CLUSTER = (CLUSTER_ANCHOR,
           neighbour_at(CLUSTER_ANCHOR[0], CLUSTER_ANCHOR[1], 0),
           neighbour_at(CLUSTER_ANCHOR[0], CLUSTER_ANCHOR[1], 1))

HP_FAVOURABLE = 400000
HP_WITNESS = 1

# `FixMath_NET_Fix64__op_Implicit(0xa)` du corps natif -- le pas du custom, par ennemi de la zone.
# Re-expose ici pour que la garde n'ait pas a le re-ecrire (source unique = le playbook).
ENEMY_STEP = 10.0


# ------------------------------------------------------------------------------ montage (live)

def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _duel(args, state: Path, rid: int) -> None:
    _run(args + ["--state-file", str(state), "--runner", str(rid)])


def write_graft_seed_bc(on=None) -> None:
    """Greffe `ActiveAbilities = [1148]` sur chaque unite de `on` dans une COPIE de la seed BC.

    `on = None` -> `[GRAFT_ON]` (le montage historique, mono-porteur). Le montage BURNING en greffe
    DEUX : un ALLUMEUR (qui caste, donc part en cooldown) et un DECIDEUR (dont on mesure la
    decision au MEME tour) -- cf. `build_burning`."""
    import rl_collect_batch as R
    targets = list(on or [GRAFT_ON])
    bc = R._load_seed_bc(None)
    seen = set()
    for u in bc.get("Units") or []:
        if u.get("Id") in targets:
            u["ActiveAbilities"] = [DAEMONIC]
            seen.add(u.get("Id"))
    missing = [t for t in targets if t not in seen]
    if missing:
        raise SystemExit("greffe impossible : %r absent(s) de BC.Units" % (missing,))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")


def _dv(rid: int) -> dict:
    import probe_27_3_live as L
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def build(hp_target: int, state: Path, board: str = BOARD) -> int:
    write_graft_seed_bc()
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    _run(["build", "--seed", str(SEED), "--board", board, "--rank", RANK,
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(state)] + extra)
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    placement = ((ids[A_VID], CLUSTER[0]), (ids[B_VID], CLUSTER[1]), (ids[C_VID], CLUSTER[2]),
                 (ids[CASTER_VID], CASTER_TILE))
    for unit, to in placement:
        _duel(["act", "move", "--unit", str(unit), "--to", "%d,%d" % to], state, rid)
    return rid


def spawn_groups(state_name: str):
    """Les `SpawnPointGroups` du SpawnPointSet ACTIF, lus dans la BC que le runner EXECUTE.

    `rl_duel build` ecrit la BC normalisee dans son state-file : c'est litteralement l'objet que
    `buildRunner` a consomme, donc la MEME structure que `BattleQuery+0x78`
    (`Board.SpawnPointSets[SpawnPointSetIndex].SpawnPointGroups`). Aucun RPC ne l'expose par runner
    -- c'est le residu d'outillage nomme par `case-302`."""
    from engine.services.machine_of_war_position import spawn_groups_from_battle_config
    p = LOGS / state_name
    if not p.exists():
        return None
    return spawn_groups_from_battle_config(json.loads(p.read_text(encoding="utf-8")).get("bc") or {})


def _caster_state(rid: int, vid: str = CASTER_VID):
    """`(id, cooldown, toActivate, present)` de 1148 chez `vid`.

    ⚠ `present` n'est PAS decoratif : apres un cast, 1148 SORT du kit rendu par `decisionView`
    (mesure #359-r3, runner 216 -- `abilities = [69]` seul, alors que `allAbilities: True`). Lire
    seulement le `cooldown` d'une entree ABSENTE rend `None`, qui se lit exactement comme
    « cooldown purge » : un `_wait_ready` qui ne teste pas la presence sort IMMEDIATEMENT et la
    mesure suivante se fait sans l'ability, en silence."""
    c = next((u for u in (_dv(rid).get("units") or []) if u.get("visualId") == vid), None)
    if c is None:
        return None, None, None, False
    ab = next((a for a in (c.get("abilities") or []) if a.get("id") == DAEMONIC), None)
    return c.get("id"), (ab or {}).get("cooldown"), _dv(rid).get("toActivate"), ab is not None


def build_ready(hp_target: int, state_name: str, board: str = BOARD) -> int:
    """Monte le montage PUIS purge le cooldown initial de 1148 (`initialCooldownTurns = 1`).

    Les fins de tour ne sont PAS cosmetiques : tant que `RemainingCooldownTurns > 0`, le natif ne
    PEUT PAS proposer l'ability, et la mesure ne dirait rien du ciblage tuile. Les positions
    crafttees survivent (on termine les tours a vide)."""
    state = LOGS / state_name
    rid = build(hp_target, state, board)
    for _ in range(4):
        cid, cd, to_act, present = _caster_state(rid)
        if cid is not None and cd in (None, 0) and cid in (to_act or []):
            return rid
        _duel(["act", "endturn"], state, rid)
    raise SystemExit("cooldown de 1148 jamais purge sur le runner %d" % rid)


# =========================== montage BURNING (#359-r3) : la zone BRULE ===========================
#
# CE QUE CE MONTAGE MESURE, ET QUE `--decision` NE PEUT PAS MESURER
# -----------------------------------------------------------------
# `DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur `GetAllDamageableTargets` = les
# ENNEMIS debout sur une tuile DEJA EN FEU de la zone. Or le SEUL poseur de ce feu est l'etage [5]
# du behaviour de 1148 elle-meme (`AddEffect(Fire -> zone)`). Sur un board frais le selecteur est
# donc VIDE et le terme de prediction vaut REELLEMENT 0 -- c'est le regime de `--decision`, ou
# brancher la prediction ne change RIEN. Le seul regime qui exerce le branchement se monte en
# CASTANT 1148 une premiere fois, puis en re-mesurant la decision au tour suivant.
#
# LA GEOMETRIE, ET POURQUOI ELLE SEPARE (l'argmax DOIT changer, sinon le lot ne conclut rien)
# -------------------------------------------------------------------------------------------
# `dir` vaut 1 sur `MC1_67` -> zone(X) = {X, X+S, X+SE}. On monte DEUX ancres candidates :
#   * `P_COLD` porte TROIS ennemis (toute sa zone), aucun en feu
#         -> custom = 3 x 10 = 30, terme de prediction = 0 ;
#   * `P_HOT`  porte DEUX ennemis, tous deux sur une tuile EN FEU
#         -> custom = 2 x 10 = 20, terme de prediction = 2 x U_dmg.
# SANS le branchement le port elit `P_COLD` (30 > 20) ; AVEC, il elit `P_HOT` des que
# 2 x U_dmg > 10. Le natif, lui, tranche -- et c'est exactement la question binaire de la tranche.
#
# POURQUOI L'ECART DE CUSTOM EST DE 10, ET PAS 20 (mesure, pas gout) : `U_dmg` est le composite
# Damage, RELATIF aux PV MAX de la cible. Le faire monter en abaissant les PV monte AUSSI l'utilite
# de l'ATTAQUE NORMALE, qui vise les memes unites -- mesure a `--hot-hp 8000` :
# `_best_attack.full = 166.98` contre `70.0` pour 1148, le natif ATTAQUE et 1148 n'est plus elue du
# tout. On ne cherche donc PAS un gros `U_dmg` : on reduit l'ECART DE CUSTOM a franchir (un ennemi),
# et on le franchit avec DEUX events sur des cibles increvables.
#
# DEUX LEVIERS DE PILOTAGE, tous deux requis :
#   * `ActiveAbilityLevel = 50` sur le DECIDEUR : au niveau du rank les bornes saturent au PLANCHER
#     (`param_8 = null` -> pierce 0, armure PLEINE) et U_dmg serait inobservable -- c'est le meme
#     regime `(3, 3, 3)` que #359-r1 avait du casser pour separer ses valeurs ;
#   * armure 0 sur les ennemis CHAUDS : meme raison, c'est le pierce nul qui l'exige.
# Le feu est pose par un cast REEL (aucun autre chemin ne le pose) et les tours se terminent A VIDE
# (`act endturn`, l'IA adverse ne joue pas) : les positions craftees survivent.

BURN_LEVEL = 50
# `AbilityVariablesMultiplierPercentage` du DECIDEUR. `minDmg`/`maxDmg` sont dans
# `variablesAffectedByRarityBonus` de `DaemonicOrdnance`, donc `AbilityConfiguration` les multiplie
# par `mult / 100`. C'est le levier qui fait franchir a `2 x U_dmg` l'ecart de custom d'UN ennemi
# (10) : a 100 % les deux events valent `6.99` a eux deux (mesure), il en faut > 10. Il agit sur la
# SEULE 1148 -- l'attaque normale, elle, ne lit pas ce champ -- donc il separe sans deformer le
# comparatif ability/attaque, contrairement a une baisse de PV.
BURN_MULT = 400
BURN_ARMOR = 0
# PV de TOUTES les cibles. Assez HAUT pour que l'attaque normale reste non competitive (le composite
# Damage est relatif aux PV max), assez BAS pour que deux events de 1148 pesent plus que l'ennemi de
# custom qui les separe. Valeur RE-MESUREE par le probe, jamais supposee : il imprime
# `_best_attack.full` a cote du `full` de 1148, et la garde EXIGE que 1148 l'emporte.
HP_BURNING = 150000
# Ancre FROIDE : le couple d'ennemis. Ancre CHAUDE : le solo, sur la tuile qu'on embrase.
BURN_COLD_ANCHOR = (4, 4)
BURN_HOT_DIR_STEPS = 3            # nb de pas (direction NORD) entre l'ancre froide et l'ancre chaude
BURN_CASTER_TILE = (1, 3)         # hors des DEUX zones, hors contact -- position PILOTEE
BURN_IGNITER = "deathPutrifier"   # SECOND porteur greffe : il caste (et part en cooldown), le
BURN_IGNITER_TILE = (2, 2)        # DECIDEUR garde son 1148 pour le MEME tour
BURN_PARK = (0, 8)                # parking des unites parasites (summons compris)
# CINQ adverses SANS invocation automatique -- les TROIS premieres remplissent la zone FROIDE, les
# DEUX dernieres la zone CHAUDE. `astraCreed` (montage `--decision`) est ecarte : il fait apparaitre
# `astraSmnKell`, qui occupait l'ancre chaude et faussait le placement. Mesure, pas supposition (le
# probe RE-LIT les positions apres placement et refuse un montage ou une unite n'est pas la ou on
# l'a mise).
#
# ⚠ L'ORDRE COMPTE, et il est MESURE : a[3]/a[4] (zone CHAUDE) doivent etre des cibles qui encaissent
# vraiment. `worldTerminator` y rendait `(0, 76)` la ou `ultraTitus` rendait `(4191, 6288)` -- MEME
# armure (0, lue), MEME elevation (2), MEMES PV (150000) : la reduction vient de l'UNITE, pas du
# montage. Il est donc range en zone FROIDE, ou seul son COMPTE importe.
BURN_A_UNITS = "necroWarden,worldKharn,worldTerminator,ultraTitus,orksWarboss"


def _step(pos, direction, n):
    for _ in range(int(n)):
        pos = neighbour_at(pos[0], pos[1], int(direction))
    return tuple(pos)


def burn_geometry(groups, team) -> dict:
    """Positions du montage BURNING, DERIVEES de `dir` -- jamais ecrites en dur.

    `dir` = `If(IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4))` calcule par le mirror de
    `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer` sur les `SpawnPointGroups` de
    la BC REELLEMENT executee. Les deux ancres sont separees de `BURN_HOT_DIR_STEPS` pas dans la
    direction NORD (3) : leurs zones-triangles sont alors DISJOINTES quel que soit `dir` (les deux
    coins portes, 1 = {S, SE} et 4 = {NW, N}, ne s'etendent que d'UN pas)."""
    from engine.services.machine_of_war_position import machine_of_war_position_for_player
    from engine.entities.selectors.geometry import _TRIANGLE_SHAPE_DIRECTIONS
    if groups is None or team is None:
        return {"dir": None}
    d = 1 if int(machine_of_war_position_for_player(groups, int(team))) == 2 else 4
    dirs = _TRIANGLE_SHAPE_DIRECTIONS[d]
    cold = tuple(BURN_COLD_ANCHOR)
    # Zone FROIDE : l'ancre + ses DEUX voisines du coin -> TROIS ennemis, custom 30.
    cold_slots = [cold] + [tuple(neighbour_at(cold[0], cold[1], k)) for k in dirs]
    hot = _step(cold, 3, BURN_HOT_DIR_STEPS)                   # ancre chaude, hors zone de `cold`
    # Zone CHAUDE : l'ancre + UNE voisine du coin -> DEUX ennemis, custom 20. Les deux tuiles sont
    # dans la zone que le cast de l'ALLUMEUR embrase, donc les deux ennemis brulent.
    hot_slots = [hot, tuple(neighbour_at(hot[0], hot[1], dirs[0]))]
    zone_cold = set(cold_slots)
    zone_hot = {hot} | {tuple(neighbour_at(hot[0], hot[1], k)) for k in dirs}
    # Le caster se pose HORS des deux zones (il ne doit ni bruler ni gonfler un custom) et hors
    # contact (sinon l'attaque normale ecrase tout et le montage ne mesure plus le ciblage).
    cpos = tuple(BURN_CASTER_TILE)
    return {"dir": d, "dirs": dirs, "cold": cold, "hot": hot,
            "cold_slots": cold_slots, "hot_slots": hot_slots,
            "caster": cpos, "zone_cold": sorted(zone_cold), "zone_hot": sorted(zone_hot),
            "zones_disjoint": not (zone_cold & zone_hot),
            "caster_outside": cpos not in (zone_cold | zone_hot)}


def build_burning(state_name: str, board: str = BOARD, hp_target: int = HP_BURNING,
                  hot_count: int = 2) -> tuple:
    """Monte le montage BURNING et rend `(rid, geometry, caster_id)`.

    DEUX PORTEURS, et c'est la piece centrale du montage : 1148 SORT du kit apres son cast (mesure
    #359-r3, runner 216 : `decisionView.abilities = [69]` seul, `allAbilities: True` compris), et
    le feu ne dure que `DefaultAmountOfRounds(5) = 2` rounds. Un montage mono-porteur devrait donc
    attendre la fin d'un cooldown QUI SURVIT au feu -- regime inatteignable. On greffe donc 1148 sur
    DEUX unites du meme camp : un ALLUMEUR, qui caste et part en cooldown, et le DECIDEUR, dont on
    mesure la decision DANS LE MEME TOUR d'equipe, 1148 intacte et la zone deja embrasee.

    Etapes, dans l'ordre -- chacune est une CONDITION du regime, pas un ornement :
      1. build (1148 greffee sur les DEUX porteurs, niveau 50 sur le decideur, armure 0 sur les
         ennemis chauds) ;
      2. placement PILOTE des cinq ennemis, de l'allumeur et du decideur (`act move`) ;
      3. purge du `initialCooldownTurns = 1` (`act endturn` A VIDE : l'IA adverse ne joue pas,
         donc les positions craftees survivent) ;
      4. l'ALLUMEUR caste 1148 sur `P_HOT` -- le seul chemin qui pose `Fire` (5) sur la zone. Aucun
         ennemi n'y brule encore, donc `GetAllDamageableTargets` est VIDE et le cast ne frappe
         personne : il ne fait qu'embraser ;
      5. AUCUN endturn ensuite -- le decideur joue dans le meme tour."""
    state = LOGS / state_name
    a_units = BURN_A_UNITS.split(",")
    write_graft_seed_bc([CASTER_VID, BURN_IGNITER])
    _run(["build", "--seed", str(SEED), "--board", board, "--rank", RANK,
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", BURN_A_UNITS,
          "--hp-target", str(hp_target),
          "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d"
                         % (CASTER_VID, BURN_LEVEL, BURN_MULT),
          # Les ennemis CHAUDS : armure 0. `param_8 = null` donne pierce 0, donc l'armure est PLEINE
          # et l'armure d'un rank normal ecraserait le degat au plancher `(3, 3, 3)`. `--hp-target`
          # met deja `Armor = 0` sur tout le camp ; on le REDIT explicitement pour ne pas dependre
          # d'un effet de bord d'un autre drapeau.
          "--unit-stat", "%s:Armor=%d,FixedArmor=%d;%s:Armor=%d,FixedArmor=%d"
                         % (a_units[3], BURN_ARMOR, BURN_ARMOR,
                            a_units[4], BURN_ARMOR, BURN_ARMOR),
          "--state-file", str(state)])
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    try:
        return _burn_stage(rid, state, state_name, a_units, hot_count)
    except BaseException:
        dispose(rid)                       # jamais de runner orphelin sur un echec de MONTAGE
        raise


def _burn_stage(rid: int, state: Path, state_name: str, a_units: list, hot_count: int) -> tuple:
    """Placement + purge de cooldown + PREMIER CAST -- la partie du montage qui peut ECHOUER.

    `hot_count` = nombre d'ennemis places sur des tuiles EN FEU. `2` = le bras qui SEPARE (le terme
    renverse l'ecart de custom) ; `1` = le bras TEMOIN (l'ecart de custom vaut DEUX ennemis, un seul
    event ne suffit pas -> le natif ET le port doivent rester sur l'ancre FROIDE). Sans le temoin,
    un port qui prefererait la zone brulante SYSTEMATIQUEMENT passerait le bras separant."""
    geo = burn_geometry(spawn_groups(state_name), _current_team(rid))
    if geo.get("dir") is None:
        raise SystemExit("SpawnPointGroups non lus -> `dir` indecidable, montage abandonne")
    if not (geo.get("zones_disjoint") and geo.get("caster_outside")):
        raise SystemExit("geometrie invalide (zones jointes ou caster dedans) : %s" % geo)
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    # Les tuiles du CASTER et de l'ALLUMEUR sont des PREFERENCES, pas des constantes : `dir` bascule
    # d'un plateau a l'autre, donc les deux zones bougent, et une position ecrite en dur y tombe
    # dedans (mesure sur `C1_03`, `dir = 4` : `(1,3)` entre en collision avec la zone FROIDE). On
    # les RESOUT sur le board reel -- marchable, hors des deux zones, hors des ancres.
    occupied = {tuple(p) for p in geo["cold_slots"]} | set(map(tuple, geo["zone_cold"])) \
        | set(map(tuple, geo["zone_hot"]))
    walk = _walkable(rid)
    cpos = _pick_tile(walk, occupied, tuple(BURN_CASTER_TILE))
    ipos = _pick_tile(walk, occupied | {cpos}, tuple(BURN_IGNITER_TILE))
    geo["caster"], geo["igniter"] = cpos, ipos

    def _place(want: dict) -> None:
        """Place chaque unite NOMMEE ; toute autre (summon apparu au premier tour) part au PARKING.
        Le montage ne subit pas la geometrie de spawn, il la pilote -- et il RE-LIT le resultat."""
        for vid, uid in ids.items():
            _duel(["act", "move", "--unit", str(uid), "--to", "%d,%d" % want.get(vid, BURN_PARK)],
                  state, rid)
        got = {v: p for v, (_i, p) in _units(rid).items()}
        bad = {v: (got.get(v), p) for v, p in want.items() if got.get(v) != p}
        if bad:
            raise SystemExit("placement KO (obtenu, attendu) : %s" % bad)

    # PHASE 1 : la zone FROIDE est deja definitive ; les DEUX chauds restent au parking, le temps
    # que le cast designe les tuiles REELLEMENT embrasees.
    cold = {a_units[i]: tuple(geo["cold_slots"][i]) for i in range(3)}
    _place({**cold, CASTER_VID: tuple(geo["caster"]), BURN_IGNITER: tuple(geo["igniter"])})
    _wait_ready(rid, state, BURN_IGNITER)
    igniter = ids[BURN_IGNITER]
    _duel(["act", "ability", "--caster", str(igniter), "--ability", str(DAEMONIC),
           "--to", "%d,%d" % tuple(geo["hot"])], state, rid)
    # PHASE 2 : les tuiles en feu sont MESUREES, pas deduites de la geometrie. `GetTargetAreaTiles`
    # finit par `TilesOnSameElevation(..., maxDiff = 1)` et `AddEffectOperation` n'allume pas une
    # tuile non marchable (residu #359-r4) : la zone-triangle NOMINALE compte 3 tuiles, la zone
    # EMBRASEE en compte souvent 2 (mesure : cast sur `(4,1)` -> `{(4,1), (5,2)}`, `(4,2)` exclue).
    # Placer les chauds sur la geometrie nominale mettait donc l'un des deux HORS du feu, et le
    # montage rendait UN event au lieu de deux -- en silence.
    fire = _fire_now(rid)
    hot_slots = [p for p in fire if p in set(map(tuple, geo["zone_hot"]))]
    if len(hot_slots) < hot_count:
        raise SystemExit("zone chaude : %d tuile(s) en feu seulement (%s) -- il en faut %d"
                         % (len(hot_slots), fire, hot_count))
    geo["hot_slots"] = hot_slots[:hot_count]
    hot = {a_units[3 + i]: geo["hot_slots"][i] for i in range(hot_count)}
    _place({**cold, **hot,
            CASTER_VID: tuple(geo["caster"]), BURN_IGNITER: tuple(geo["igniter"])})
    # AUCUN endturn : le DECIDEUR joue dans le MEME tour d'equipe, 1148 intacte.
    caster = _assert_ready(rid, CASTER_VID)
    return rid, geo, caster


def _walkable(rid: int) -> dict:
    """`{(col,row): bool}` du `boardGraph` -- `BattleQuery$$IsWalkableTile`. Une tuile non marchable
    ne peut jamais accueillir d'unite : y envoyer un `act move` echoue en silence et l'unite reste ou
    elle etait, ce qui se lit ensuite comme un placement « presque bon »."""
    import engine_validate as EV
    import probe_27_3_live as L
    from engine.ai import context as C
    sid = L.INV._session_id()
    return C._board_walkable(lambda m, b, t=60: EV._r(sid, m, b, t), rid)


def _pick_tile(walkable: dict, forbidden: set, prefer: tuple) -> tuple:
    """`prefer` si elle est marchable et hors `forbidden` ; sinon la tuile marchable autorisee la
    PLUS PROCHE (distance hex, puis ordre lexicographique -- deterministe)."""
    if walkable.get(tuple(prefer)) and tuple(prefer) not in forbidden:
        return tuple(prefer)
    cands = [p for p, ok in walkable.items() if ok and p not in forbidden]
    if not cands:
        raise SystemExit("aucune tuile marchable hors des zones pour placer %s" % (prefer,))
    return min(cands, key=lambda p: (hexgeo.distance(p, tuple(prefer)), p))


def _fire_now(rid: int) -> list:
    """Positions portant `Fire` (5), lues FRAICHES dans `tileMeta` -- le meme canal que
    `Scene.tile_effects_by_pos`, indexe par NOM d'effet (`effects[].name`)."""
    import probe_27_3_live as L
    from engine.entities.effect_type import EffectType
    tm = L._rpc("tileMeta", [{"runnerId": rid}])
    return sorted((t.get("col"), t.get("row")) for t in (tm.get("tiles") or [])
                  if EffectType.Fire.name in [e.get("name") for e in (t.get("effects") or [])])


def _current_team(rid: int):
    from engine.ai.context import _current_player_team
    return _current_player_team(_dv(rid))


def _assert_ready(rid: int, vid: str) -> int:
    """1148 PRESENTE au kit de `vid`, hors cooldown, et `vid` activable -- sinon le montage est
    abandonne. Le test de PRESENCE est le garde-fou : apres un cast, 1148 sort du kit et un simple
    `cooldown is None` se lit comme « purge » (cf. `_caster_state`)."""
    cid, cd, to_act, present = _caster_state(rid, vid)
    if cid is None or not present or cd not in (None, 0) or cid not in (to_act or []):
        raise SystemExit("%s non pret : id=%s present=%s cooldown=%s activable=%s"
                         % (vid, cid, present, cd, cid in (to_act or [])))
    return cid


def _wait_ready(rid: int, state: Path, vid: str = CASTER_VID, tries: int = 6) -> int:
    """`act endturn` A VIDE jusqu'a ce que `vid` soit activable, 1148 PRESENTE et hors cooldown."""
    for _ in range(tries):
        cid, cd, to_act, present = _caster_state(rid, vid)
        if cid is not None and present and cd in (None, 0) and cid in (to_act or []):
            return cid
        _duel(["act", "endturn"], state, rid)
    raise SystemExit("%s jamais pret (1148 absente ou en cooldown) sur le runner %d" % (vid, rid))


def engine_burning(rid: int, caster: int, groups) -> dict:
    """Decision MOTEUR sur l'etat BRULANT + le bras `nopred` (l'etat d'AVANT #359-r3).

    `nopred` remet `make_damage_predictions` sur le corps de BASE de `NonAttackComparablePlaybook`
    (`return []`) : c'est LITTERALEMENT le port d'avant cette tranche, reconstitue, jamais
    re-implemente. Un `nopred == on` signifie que le montage n'exerce pas le branchement."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook.nonattack import NonAttackComparablePlaybook
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)              # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor, spawn_groups=groups)
    pb = PB.REGISTRY[DAEMONIC]
    pos_by_tid = {t: p for p, t in (ctx.tile_id_by_pos or {}).items()}

    rows = []
    for t in pb.eligible_targets(ctx, DAEMONIC):
        cu = pb.calculate_custom_utility(ctx, ctx.origin, t, DAEMONIC)
        evs = pb.make_damage_predictions(ctx, ctx.origin, t, DAEMONIC)
        up = (pb.calculate_utility_from_predictions(ctx, ctx.origin, t, DAEMONIC, evs)[0]
              if evs else 0.0)
        rows.append({"tile": t, "pos": pos_by_tid.get(t), "custom": cu,
                     "n_events": len(evs), "u_pred": up, "u": cu + up,
                     "events": [(e.target, e.prediction.accurate_health_damage.min,
                                 e.prediction.accurate_health_damage.max,
                                 e.prediction.applied_hits) for e in evs]})
    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor, spawn_groups=groups)
    # ⚠ RESTAURATION PAR SAUVEGARDE, jamais par `del` : `type(pb)` DEFINIT `make_damage_predictions`
    # (c'est tout l'objet de cette tranche). Un `del` apres l'avoir ecrase supprimerait la methode
    # PROPRE de la classe, et la resolution retomberait DEFINITIVEMENT sur le corps de base --
    # toute mesure ulterieure du meme process lirait alors un port DEGRADE, en silence. Mesure :
    # `cand_1148` rendait `pred = 20.0` (custom seul) apres ce bras, runner 218.
    saved = type(pb).__dict__.get("make_damage_predictions")
    type(pb).make_damage_predictions = NonAttackComparablePlaybook.make_damage_predictions
    try:
        nopred = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor,
                                  spawn_groups=groups)
        nopred_rows = [{"tile": r["tile"], "pos": r["pos"], "u": r["custom"]} for r in rows]
    finally:
        if saved is not None:
            type(pb).make_damage_predictions = saved
        else:
            del type(pb).make_damage_predictions
    fire = sorted({p for p, names in (ctx.scene.tile_effects_by_pos or {}).items()
                   if "Fire" in (names or [])})
    # DECOMPOSITION du choix D'ABILITY (et pas seulement de la CIBLE de 1148) : le `Bucket` compare
    # `full` de la route non-attaque a `full` de `_best_attack`. Sans ces deux nombres, un « le natif
    # attaque » ne dit pas si 1148 a perdu de 0.2 ou de 40.
    from engine.playbook.nonattack import nonattack_candidates
    from engine.ai.action_generators import ComparableAbilityGenerator
    cand = [c for c in nonattack_candidates(ctx) if c.get("ability") == DAEMONIC]
    ba = ComparableAbilityGenerator()._best_attack(ctx)
    vis_by_id = {u.get("id"): u.get("visualId") for u in (dv.get("units") or [])}
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "nopred": (nopred.get("ability"), nopred.get("target")),
            "rows": rows, "nopred_rows": nopred_rows, "fire": fire,
            "mow_position": ctx.machine_of_war_position(),
            "diag": burn_diag(ctx.scene, caster, rows),
            "cand_1148": cand,
            # `nonattack_candidates` refuse une ability absente de `ctx.me` ou `usable is False` :
            # sans cette ligne, un candidat VIDE se lit comme « le port ne veut pas caster », alors
            # que c'est le KIT vu par le contexte qui manque.
            "me_ability": next((a for a in ((ctx.me or {}).get("abilities") or [])
                                if a.get("id") == DAEMONIC), None),
            "me_abilities": [a.get("id") for a in ((ctx.me or {}).get("abilities") or [])],
            "reach_nc": list(ctx.reach_nc or [])[:6],
            # `_best_attack` rend `(u, u_action, target, ability, tile)` -- c'est `u_action` (le
            # `full` du Bucket) qui est compare au `full` de la route non-attaque.
            "best_attack": ({"ability": ba[3], "target": ba[2], "full": ba[1], "u": ba[0],
                             "tile": ba[4]} if ba else None),
            "vis_by_id": vis_by_id,
            "pos_by_tid": pos_by_tid}


def burn_diag(scene, caster: int, rows: list) -> dict:
    """DECOMPOSITION PAR ETAGE des ENTREES du degat -- pour qu'un `(3, 3, 3)` (le PLANCHER) designe
    l'etage fautif au lieu d'un scalaire a fitter.

    Trois entrees, trois causes distinctes d'un plancher : le NIVEAU d'ability effectif (le
    `--unit-stat ActiveAbilityLevel` a-t-il pris ?), la BASE `AActiveAbility$$MinMaxDamage` qui en
    decoule, et l'ARMURE de la cible (avec `param_8 = null`, pierce 0 -> armure PLEINE)."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.entities.abilities.active_ability import active_ability_for
    from engine.entities.stats import StatType
    cfg = AbilityConfiguration.from_gameconfig(DAEMONIC_ID, GC.ability(DAEMONIC_ID))
    ctx0 = scene.ctx(int(caster))
    ab = (active_ability_for(DAEMONIC_ID, DAEMONIC, ctx0, cfg,
                             ability_state=scene.ability_state(int(caster), DAEMONIC))
          if (ctx0 is not None and cfg is not None) else None)
    tgts = sorted({e[0] for r in rows for e in r["events"]})
    armor = {}
    for tid in tgts:
        uc = scene.ctx(int(tid))
        armor[tid] = int(uc.get_stat(int(StatType.ARMOR), 0)) if uc is not None else None
    # L'ELEVATION est le 4e etage : `DamageCalculations` applique un modificateur positionnel selon
    # l'ecart d'elevation attaquant/defenseur. Deux cibles voisines d'armure IDENTIQUE peuvent donc
    # rendre des bornes qui n'ont rien a voir -- mesure : `(4191, 6288)` contre `(0, 76)`.
    elev = {}
    for tid in tgts + [int(caster)]:
        p = scene.pos(int(tid))
        elev[tid] = (tuple(p) if p else None,
                     (scene.elev_by_pos or {}).get(tuple(p)) if p else None)
    return {"ability_level": (ab.level if ab else None),
            "ability_multiplier": (getattr(ab, "multiplier", None) if ab else None),
            "base_damage": (ab.get_damage() if ab else None),
            "hits": (ab.get_special_hits(False) if ab else None),
            "target_armour": armor,
            "pos_elev": elev,
            "target_hpmax": {t: scene.hpmax(int(t)) for t in tgts}}


def measure_burning(state_name: str, board: str = BOARD, hp_target: int = HP_BURNING,
                    hot_count: int = 2) -> dict:
    """Le runner est dispose par l'APPELANT (`arms` du test, `burning` du CLI) -- mais jamais
    abandonne : un echec APRES le build rend quand meme son `rid` dans l'exception."""
    rid, geo, caster = build_burning(state_name, board, hp_target, hot_count)
    try:
        groups = spawn_groups(state_name)
        pos = {v: p for v, (_i, p) in _units(rid).items()}
        return {"rid": rid, "caster": caster, "geo": geo, "board": board, "positions": pos,
                "spawn_groups": groups, "native": native(rid, caster),
                "engine": engine_burning(rid, caster, groups)}
    except BaseException:
        dispose(rid)                       # jamais de runner orphelin sur un echec de mesure
        raise


def burning(hp_target: int = HP_BURNING, board: str = BOARD, hot_count: int = 2,
            state_name: str = "rs_302_3_burn.json") -> int:
    r = measure_burning(state_name, board, hp_target, hot_count)
    try:
        e, g = r["engine"], r["geo"]
        print("\n=== BURNING (runner %d, caster u%s, board %s) ===" % (r["rid"], r["caster"], board))
        print("  dir              = %s (zone = centre + %s)" % (g["dir"], list(g["dirs"])))
        print("  zone FROIDE      = %s   zone CHAUDE = %s" % (g["cold_slots"], g["hot_slots"]))
        print("  positions        = %s" % r["positions"])
        print("  tuiles EN FEU    = %s" % (e["fire"],))
        print("  MachineOfWarPos  = %s" % e["mow_position"])
        print("  ENTREES du degat = %s" % e["diag"])
        cold_t = next((x for x in e["rows"] if x["pos"] == tuple(g["cold"])), None)
        hot_t = next((x for x in e["rows"] if x["pos"] == tuple(g["hot"])), None)
        for lab, x in (("FROIDE", cold_t), ("CHAUDE", hot_t)):
            print("  ancre %-7s : %s" % (lab, {k: x[k] for k in
                                               ("tile", "pos", "custom", "n_events", "u_pred", "u")}
                                         if x else "HORS DOMAINE"))
            if x and x["events"]:
                print("      events      = %s" % (x["events"],))
        print("  1148 dans ctx.me = %s   (kit vu = %s)" % (e["me_ability"], e["me_abilities"]))
        print("  reach_nc (6 1res)= %s" % (e["reach_nc"],))
        print("  candidat 1148    = %s" % [{k: (round(v, 3) if isinstance(v, float) else v)
                                             for k, v in c.items()} for c in e["cand_1148"]])
        print("  _best_attack     = %s" % ({k: (round(v, 3) if isinstance(v, float) else v)
                                            for k, v in (e["best_attack"] or {}).items()}))
        print("  visualId par id  = %s" % e["vis_by_id"])
        top = sorted(e["rows"], key=lambda x: -x["u"])[:4]
        print("  top u (avec pred) = %s" % [(x["pos"], round(x["u"], 3)) for x in top])
        topn = sorted(e["nopred_rows"], key=lambda x: -x["u"])[:4]
        print("  top u (SANS pred) = %s" % [(x["pos"], round(x["u"], 3)) for x in topn])
        print("  natif            = %s  pos=%s" % (r["native"], e["pos_by_tid"].get(r["native"][1])))
        print("  moteur   (on)    = %s  pos=%s" % (e["on"], e["pos_by_tid"].get(e["on"][1])))
        print("  moteur (nopred)  = %s  pos=%s" % (e["nopred"],
                                                   e["pos_by_tid"].get(e["nopred"][1])))
        print("\n=== VERDICT ===")
        print("  ACCORD natif/moteur       = %s" % (e["on"] == r["native"]))
        print("  l'argmax CHANGE (on!=nop) = %s" % (e["on"] != e["nopred"]))
    finally:
        dispose(r["rid"])
    return 0


def agreement(steps: int = 24, board: str = BOARD, unbranched: bool = False,
              state_name: str = "rs_302_3_agree.json") -> int:
    """AGREEMENT sur une MARCHE ENTIERE du montage BURNING (#359-r3).

    Un accord per-event ne suffit pas ici : brancher la prediction change une UTILITE, donc
    potentiellement tout ce qui vient apres dans la trajectoire. On marche la trajectoire NATIVE
    (`aiStepDryRun` -> `applyAction`) et on compare la decision du moteur a CHAQUE pas -- 1148 est
    greffee sur DEUX unites du camp joueur, elle est donc jouee plusieurs fois dans la marche.

    `spawn_groups` est PASSE : sans lui `IsPositionMachineForCurrentPlayer` retombe sur son repli et
    1148 marche sur le mauvais triangle -- le desaccord n'accuserait alors que le harnais.
    ⚠ `run_agreement` MUTE le runner : montage dedie, jamais celui d'une mesure."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook.nonattack import NonAttackComparablePlaybook
    rid, geo, caster = build_burning(state_name, board)
    pb = PB.REGISTRY[DAEMONIC]
    saved = type(pb).__dict__.get("make_damage_predictions")
    if unbranched:                     # CONTRE-MESURE : la MEME marche avec le port d'AVANT
        type(pb).make_damage_predictions = NonAttackComparablePlaybook.make_damage_predictions
    try:
        sid = L.INV._session_id()
        res = EV.run_agreement(sid, rid, steps, W.load(),
                               spawn_groups=spawn_groups(state_name))
        pos, ab, stay = res["pos"], res["ability"], res["stay"]
        print("\n=== AGREEMENT (montage BURNING%s, runner %d, %d pas demandes) ==="
              % (" -- PORT D'AVANT (prediction DEBRANCHEE)" if unbranched else "", rid, steps))
        print("  geometrie        : FROIDE %s  CHAUDE %s" % (geo["cold_slots"], geo["hot_slots"]))
        print("  [positioning] %s moves : exact=%s  <=1hex=%s" % (pos["n"], pos["exact"],
                                                                  pos["near"]))
        print("  [ability]     %s casts : match=%s" % (ab["n"], ab["match"]))
        print("  [stay]        %s chunks : match=%s" % (stay["n"], stay["match"]))
        abil = [r for r in res["records"] if r.get("kind") == "ability"]
        bad = [r for r in abil if r.get("match") is False]
        print("  casts en DESACCORD = %d" % len(bad))
        for r in bad[:6]:
            print("    %s" % {k: r.get(k) for k in ("step", "uid", "native", "engine")})
        c1148 = [r for r in abil
                 if DAEMONIC in (tuple(r.get("native") or ()) + tuple(r.get("engine") or ()))]
        print("  casts impliquant 1148 = %d (match=%d)"
              % (len(c1148), sum(1 for r in c1148 if r.get("match"))))
        for r in c1148[:8]:
            print("    %s" % {k: r.get(k) for k in ("step", "uid", "native", "engine", "match")})
    finally:
        if unbranched:
            if saved is not None:
                type(pb).make_damage_predictions = saved
            else:
                del type(pb).make_damage_predictions
        dispose(rid)
    return 0


# ----------------------------------------------------------------------------- etages mesures

def stage(rid: int, caster: int) -> dict:
    """Kit REEL vu par `unitAbilityTypes` + domaine de cibles + slot MoW du joueur courant."""
    import probe_27_3_live as L
    from engine.ai import context as C

    dv = _dv(rid)
    me = next((u for u in (dv.get("units") or []) if u.get("id") == caster), None)
    ab = next((a for a in ((me or {}).get("abilities") or []) if a.get("id") == DAEMONIC), None)
    at = L._rpc("abilityTargets", [{"runnerId": rid, "unitId": caster, "allAbilities": True}])
    kinds, count = {}, 0
    for u in (at.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != DAEMONIC:
                continue
            count += int(a.get("targetCount") or 0)
            for t in (a.get("targets") or []):
                kinds[t.get("kind")] = kinds.get(t.get("kind"), 0) + 1
    tid_by_pos = C._board_tile_ids(lambda m, b, to=40: L._rpc(m, [dict(b)]), rid)
    mows = dv.get("mows") or []
    slot_by_player = C._mow_slot_by_player(dv)
    return {"in_kit": ab is not None, "usable": (ab or {}).get("usable"),
            "cooldown": (ab or {}).get("cooldown"), "kind": (ab or {}).get("kind"),
            "target_count": count, "target_kinds": kinds,
            "current_player": dv.get("currentPlayer"), "mow_rows": len(mows),
            "mow_slot_by_player": slot_by_player,
            "mow_slot_current": slot_by_player.get(dv.get("currentPlayer")),
            "tile_ids": len(tid_by_pos)}


def native(rid: int, caster: int) -> tuple:
    """Le choix du natif : `(abilityType, targetId)` de l'`ActiveAbilityMessage` propose."""
    import probe_27_3_live as L
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                return (m.get("abilityType"), m.get("targetId"))
    return (None, None)


def engine(rid: int, caster: int, groups=None) -> dict:
    """Decision MOTEUR sur le MEME etat + bras de necessite + decomposition par etage.

    `groups` = `SpawnPointGroups` du set actif (cf. `spawn_groups`) -- l'entree du predicat
    `IsPositionMachineForCurrentPlayer`. Le bras `nogroups` rejoue la MEME decision SANS elle :
    c'est la mesure de ce que vaut le port quand le canal manque (l'etat d'avant cette tranche)."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)              # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor, spawn_groups=groups)
    pb = PB.REGISTRY[DAEMONIC]

    targets = pb.eligible_targets(ctx, DAEMONIC)
    per_target = [(t, pb.calculate_custom_utility(ctx, ctx.origin, t, DAEMONIC)) for t in targets]
    preds = {t: len(pb.make_damage_predictions(ctx, ctx.origin, t, DAEMONIC)) for t in targets}
    # VUE ROUGE : ce que `eligible_targets` rend avec le domaine force a UNITE (l'etat d'AVANT la
    # route tuile). Mesure, pas hypothese.
    orig_dom = type(pb).targets_tiles
    type(pb).targets_tiles = lambda self, aid: False
    try:
        targets_unit_domain = pb.eligible_targets(ctx, DAEMONIC)
    finally:
        type(pb).targets_tiles = orig_dom

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor, spawn_groups=groups)
    # BRAS `nogroups` : le MEME moteur prive du canal `SpawnPointGroups`. Il mesure l'ecart que
    # produit le predicat `IsPositionMachineForCurrentPlayer` quand il retombe sur son repli --
    # c'est-a-dire l'ETAT D'AVANT cette tranche, pas une hypothese sur lui.
    nogroups = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, tile, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor,
                                spawn_groups=groups)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor,
                                   spawn_groups=groups)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    from engine.ai.action_generators import ComparableAbilityGenerator
    best = ComparableAbilityGenerator()._best_attack(ctx)
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "nogroups": (nogroups.get("ability"), nogroups.get("target")),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "targets": targets, "per_target": per_target, "pred_counts": preds,
            "targets_unit_domain": targets_unit_domain,
            "best_attack_ability": (best[3] if best else None),
            "mow_position": ctx.machine_of_war_position(),
            "current_player_team": ctx.current_player_team}


def measure(hp_target: int, state_name: str, board: str = BOARD) -> dict:
    rid = build_ready(hp_target, state_name, board)
    caster, cd, _, _ = _caster_state(rid)
    pos = {v: p for v, (_i, p) in _units(rid).items()}
    groups = spawn_groups(state_name)
    return {"rid": rid, "caster": caster, "cooldown": cd, "positions": pos, "board": board,
            "spawn_groups": groups, "stage": stage(rid, caster),
            "native": native(rid, caster), "engine": engine(rid, caster, groups)}


def dispose(rid: int) -> None:
    import probe_27_3_live as L
    try:
        L._rpc("disposeRunner", [{"runnerId": rid}])
    except Exception:                                       # noqa: BLE001
        pass


# ------------------------------------------------------------------------------------- sorties

def _print_arm(name: str, r: dict) -> None:
    e, s = r["engine"], r["stage"]
    print("\n=== bras %s (runner %d, caster u%s, board %s) ==="
          % (name, r["rid"], r["caster"], r.get("board")))
    print("  positions        = %s" % {k: v for k, v in r["positions"].items()})
    print("  cooldown 1148    = %s (doit etre None/0)" % r["cooldown"])
    print("  kit REEL         : in_kit=%s usable=%s kind=%s" % (s["in_kit"], s["usable"], s["kind"]))
    print("  domaine 1148     : %d cibles, kinds=%s" % (s["target_count"], s["target_kinds"]))
    print("  currentPlayer=%s  mows=%d  slot_by_player=%s  team courante=%s"
          % (s["current_player"], s["mow_rows"], s["mow_slot_by_player"], e["current_player_team"]))
    print("  SpawnPointGroups = %s" % ([(g.get("TeamWithPlayerIndex"),
                                         g.get("MachineOfWarPosition"))
                                        for g in (r["spawn_groups"] or [])] or "NON LUS"))
    print("  MachineOfWarPosition(joueur courant) = %s (2 = Bottom -> triangle {S,SE})"
          % e["mow_position"])
    print("  natif            = %s" % (r["native"],))
    print("  moteur           = %s (to=%s)" % (e["on"], e["to"]))
    print("  nogroups         = %s   (canal SpawnPointGroups coupe)" % (e["nogroups"],))
    print("  zero  (custom=0) = %s" % (e["zero"],))
    print("  noroute          = %s" % (e["noroute"],))
    print("  best_attack rend = %s" % e["best_attack_ability"])
    print("  eligibles        = %d tuiles | domaine UNITE force = %s"
          % (len(e["targets"]), e["targets_unit_domain"]))
    vals = sorted({c for _t, c in e["per_target"]})
    print("  custom distinct  = %s" % vals)
    print("  predictions !=0  = %d cible(s) (attendu 0 : la zone ne brule pas)"
          % sum(1 for n in e["pred_counts"].values() if n))
    print("  ACCORD           = %s" % ("OUI" if e["on"] == r["native"] else "NON"))


def decision(hp_fav: int, hp_wit: int) -> int:
    rids = []
    try:
        a = measure(hp_fav, "rs_302_3_a.json")
        rids.append(a["rid"])
        _print_arm("favorable", a)
        b = measure(hp_wit, "rs_302_3_b.json")
        rids.append(b["rid"])
        _print_arm("TEMOIN", b)
        print("\n=== VERDICT ===")
        print("  natif caste 1148 au bras favorable : %s" % (a["native"][0] == DAEMONIC))
        print("  natif caste 1148 au bras TEMOIN    : %s (doit etre False)"
              % (b["native"][0] == DAEMONIC))
        print("  accord des deux bras               : %s"
              % (a["engine"]["on"] == a["native"] and b["engine"]["on"] == b["native"]))
    finally:
        for rid in rids:
            dispose(rid)
    return 0


def flip(hp_target: int) -> int:
    """SECOND CAS DISCRIMINANT : le MEME montage sur un plateau dont le groupe de spawn declare
    `MachineOfWarPosition = 0`.

    `MC1_67` (SpawnPointSetIndex 1) declare `(TWPI 0 -> 2)`, donc le predicat est VRAI et le
    triangle vaut `{S, SE}`. `C1_03` declare `(0, 0)` pour les DEUX camps : le predicat devient
    FAUX et le triangle bascule sur `{NW, N}`. Le natif ET le port doivent changer de cible
    ENSEMBLE. Sans ce bras, l'accord de `--decision` ne distinguerait pas « le port lit le groupe »
    de « le port repond VRAI par hasard ».

    Le cluster est le meme (A, A+S, A+SE) : sous `{S, SE}` la tuile A capte les TROIS ennemis
    (custom 30), sous `{NW, N}` aucune tuile n'en capte plus de DEUX (custom 20)."""
    r = measure(hp_target, "rs_302_3_f.json", BOARD_FLAT)
    try:
        _print_arm("FLIP (" + BOARD_FLAT + ", groupe a MoWPos 0)", r)
        e = r["engine"]
        vals = sorted({c for _t, c in e["per_target"]})
        print("\n=== VERDICT FLIP ===")
        print("  MachineOfWarPosition attendue 0, mesuree %s" % e["mow_position"])
        print("  custom max = %s (30 = triangle {S,SE} ; 20 = triangle {NW,N})"
              % (vals[-1] if vals else None))
        print("  ACCORD = %s" % (e["on"] == r["native"]))
    finally:
        dispose(r["rid"])
    return 0


def stage_only(hp_target: int) -> int:
    rid = build_ready(hp_target, "rs_302_3_s.json")
    try:
        caster, _cd, _, _ = _caster_state(rid)
        st = stage(rid, caster)
        print("runner=%d caster=u%s" % (rid, caster))
        for k, v in st.items():
            print("  %-20s = %s" % (k, v))
        print("  cluster vise    = %s" % (CLUSTER,))
        print("  voisins ancre   = %s" % (hexgeo.neighbors(*CLUSTER_ANCHOR),))
    finally:
        dispose(rid)
    return 0


def diag(hp_target: int) -> int:
    """DECOMPOSITION PAR ETAGE d'un desaccord de CIBLE : pour chaque tuile candidate, sa position,
    la ZONE que le port calcule (`GetTargetAreaTiles`), le custom, et l'utilite d'action complete.

    C'est l'outil a sortir AVANT toute retouche : « le natif vise 52, le port 53 » ne dit pas si
    c'est la DIRECTION du triangle, l'ORDRE d'enumeration (tie-break keep-first) ou le terme
    positionnel qui differe -- et les trois se corrigent a des endroits opposes."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook.base import tile_utility
    from engine.playbook.tile_targets import dsl_context_for_tile_target
    from engine.entities.selectors.accessors import FixedTileIds
    from engine.runner.abilities.blacklegion import daemonic_ordnance_target_area_tiles
    from engine.ai import context as AICTX

    rid = build_ready(hp_target, "rs_302_3_d.json")
    try:
        caster, _cd, _, _ = _caster_state(rid)
        nat = native(rid, caster)
        sid = L.INV._session_id()
        rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, W.load(),
                          _scene.build_predictor(rpc, rid),
                          spawn_groups=spawn_groups("rs_302_3_d.json"))
        pb = PB.REGISTRY[DAEMONIC]
        print("MachineOfWarPosition(courant) = %s (team %s)"
              % (ctx.machine_of_war_position(), ctx.current_player_team))
        dctx = dsl_context_for_tile_target(ctx)
        pos_by_tid = {t: p for p, t in (ctx.tile_id_by_pos or {}).items()}
        targets = pb.eligible_targets(ctx, DAEMONIC)
        rows = []
        for i, t in enumerate(targets):
            u = pb.calculate_custom_utility(ctx, ctx.origin, t, DAEMONIC)
            zone = daemonic_ordnance_target_area_tiles(FixedTileIds([int(t)])).select(dctx)
            rows.append((i, t, pos_by_tid.get(t), u, [pos_by_tid.get(z) for z in zone]))
        print("runner=%d caster=u%s natif=%s" % (rid, caster, (nat,)))
        print("occupants = %s" % {v: p for v, (_i, p) in _units(rid).items()})
        print("\nordre  tile  pos      custom  zone (positions)")
        for i, t, p, u, zone in rows:
            if u > 0 or t in (nat[1],):
                print("  %-4d %-5s %-8s %-6s %s%s"
                      % (i, t, p, u, zone, "   <== NATIF" if t == nat[1] else ""))
        # Terme positionnel : `full = custom + tile_utility(T)` sur la MEILLEURE tuile d'action.
        best_by_tile = {}
        for T in (ctx.reach_nc or []):
            best_by_tile[T] = tile_utility(ctx, T)
        print("\ntile_utility par tuile d'action (les 6 premieres) = %s"
              % list(best_by_tile.items())[:6])
        top = sorted(rows, key=lambda r: -r[3])[:6]
        print("top custom = %s" % [(r[1], r[2], r[3]) for r in top])
    finally:
        dispose(rid)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision", action="store_true")
    ap.add_argument("--flip", action="store_true")
    ap.add_argument("--burning", action="store_true")
    ap.add_argument("--agreement", action="store_true")
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--unbranched", action="store_true")
    ap.add_argument("--hot-count", type=int, default=2)
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--stage", action="store_true")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--hp-target", type=int, default=HP_FAVOURABLE)
    ap.add_argument("--hp-witness", type=int, default=HP_WITNESS)
    a = ap.parse_args()
    if a.decision:
        return decision(a.hp_target, a.hp_witness)
    if a.agreement:
        return agreement(a.steps, a.board, a.unbranched)
    if a.burning:
        return burning(a.hp_target if a.hp_target != HP_FAVOURABLE else HP_BURNING, a.board,
                       a.hot_count)
    if a.flip:
        return flip(a.hp_target)
    if a.diag:
        return diag(a.hp_target)
    if a.stage:
        return stage_only(a.hp_target)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
