"""GARDE #490 -- face COMBAT de `1027 PsychicMaelstrom` (Sibyll `astraPrimarisPsy`).

Ce que ces tests EMPECHENT de re-casser, et pourquoi chacun existe :

1. `test_hits_node_offline` -- la STRUCTURE du noeud de coups. Le natif
   (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicMaelstromAbility$$ExecuteBehaviour`)
   compose `Multiply(Sum(Direct(1), 4 x ConditionalAmount(Maybe(chance_i), Direct(1))),
   Direct(nrOfHits))`. Le test pilote un RNG-temoin : il verifie les BORNES (1..5 x nrOfHits),
   l'ORDRE des quatre chances tirees (`chance, chance_2, chance_3, chance_4` = celui de
   `SumAmount$$Calculate`, qui evalue a..e), le COMPTE de tirages (exactement 4, un par `Maybe`),
   et la degradation `rng=None` (branche `!CanUseRandom` du natif = `99 < chance` = 1 seul coup,
   ce que predit le playbook). Un port qui figerait `hits` -- la faute qu'aurait produite le choix
   de la surcharge `hits:System.Int32` de `DSLBehaviors$$AttackWithAbilityDamage` -- tombe ici.

2. `test_registre_offline` -- les DEUX donnees obligatoires du registre posees ENSEMBLE
   (`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE`), et la DISJONCTION avec
   `TARGETING_OPTIONS_UNPORTED` (une ability a UNE source de masque, jamais deux). Sans
   `TARGETING_OPTIONS`, `get_invalid_target_reason` rend 0 immediatement : degradation PERMISSIVE,
   invisible en self-play.

3. `test_damage_bit_exact_live` -- la face EXECUTER, par REPLAY-DIFF repete. Assert
   `last['ported'] is True` (sans lui le cast est un no-op silencieux) PUIS accord bit-exact des
   deltas HP live/offline sur plusieurs casts, en EXIGEANT que le nombre de coups VARIE (temoin
   non-degenere : un accord obtenu uniquement sur des casts a 1 coup ne discriminerait pas).
   MESURE de reference (`probe_490_psychic_maelstrom.py`, seed 49001, board MC1_67) : 8/8 casts
   bit-exacts, coups observes {2, 3, 4}. CONTRE-EPREUVE (`probe_490_contre_epreuve.py`) : avec un
   `hits` fige a 1, le controle ROUGIT sur 4/4 -- y compris sur le cast ou le live n'a fait qu'UN
   coup (3424 live vs 3461 offline), parce que les quatre `NextBool` non consommes DECALENT le flux
   `IntBasedMersenneTwister` et donc le tirage de degat lui-meme.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus les fixtures `autouse`, dont le verdict
        # de CHAQUE test depend.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        # ... y compris les DEUX conftest intermediaires du chemin de ce fichier, qui portent
        # les fixtures de montage (`build_runner`/`rpc`) dont chaque test live depend.
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Le perimetre est pris LARGE et non feuille a feuille : la
        # FERMETURE D'IMPORTS mesuree par le cliquet compte 134 modules d'`engine/**`
        # (le chargement d'une ability tire le registre, le vocabulaire DSL, les Operations,
        # l'IA et le pathfinding), et une liste choisie serait un faux vert -- elle ne pourrait
        # pas montrer le module qu'elle a oublie. Les foyers VRAIMENT load-bearing, pour la
        # relecture humaine : `abilities/loki/psychic_maelstrom.py` (l'arbre), `handler.py` +
        # `attack_type.py` + `targeting.py` (les registres confrontes), `entities/formulas.py`
        # + `entities/triggers.py` (Sum/ConditionalAmount/Multiply/MaybeTrigger),
        # `abilities/behaviours/combat.py` et `operations/damage_ops/ability.py` (la route),
        # `runner/prng.py` (l'ORDRE de consommation, qui est precisement ce qu'on mesure).
        "scripts/python/engine/**/*.py",
        # Et les modules de la RACINE : la cascade des `conftest.py` de `tests/engine/runner`
        # importe une vingtaine de probes (les fixtures partagees `overkill_*`, `psychic_aoe`,
        # `ai_*`...) plus `hexgeo` / `engine_validate`. Ils entrent donc dans la fermeture de CE
        # fichier, qu'il les cite ou non -- les taire serait le faux vert que le cliquet cherche.
        "scripts/python/*.py",
        # Le KIT lui-meme : les cinq constantes (chance*, nrOfHits) et les bornes de degat
        # sont LUES du gameconfig -- un re-dump qui les bouge change ce que ce test mesure.
        "data/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "L'arbre DSL de 1027, les deux registres (masque de ciblage / AbilityAttackType) "
              "que ce fichier confronte, le vocabulaire DSL qu'il compose (Sum/ConditionalAmount/"
              "Multiply/MaybeTrigger), la route `execute_ability_attack`, le PRNG dont l'ORDRE de "
              "consommation est precisement ce qui est mesure, et le kit gameconfig d'ou sortent "
              "les quatre chances. `build: True` parce que la face EXECUTER se confronte au natif "
              "par RPC : un changement de build change le decompile dont ce port est le mirror.",
}

import pytest                                                           # noqa: E402

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.effects.magnitude import ability_var
from engine.runner.abilities.loki.psychic_maelstrom import (PsychicMaelstromAbility,
                                                            psychic_maelstrom_hits)

CASTER_VIS = "astraPrimarisPsy"       # Sibyll -- seul porteur lineup de 1027
ABILITY = int(ActiveAbilityType.PsychicMaelstrom)     # 1027
ABILITY_ID = "PsychicMaelstrom"
RANGE = 2                             # constants.range (RANGE_FROM_CONFIG)
CASTS = 6
BUILD = ["--p-units", f"{CASTER_VIS},templAncient",
         "--a-units", "ultraTitus,necroWarden",
         "--hp-target", "400000", "--hp-player", "400000"]


class _RngTemoin:
    """Substitut de `IdunBattle.Utils.PRNG.DisallowablePseudoRNG` : `next_bool` rend la suite
    fournie et ENREGISTRE la chance demandee (c'est elle qui revele l'ordre d'evaluation)."""
    def __init__(self, suite):
        self.suite = list(suite)
        self.chances = []

    def next_bool(self, chance):
        self.chances.append(int(chance))
        return bool(self.suite.pop(0))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def test_hits_node_offline():
    """Le nombre de coups est un NOEUD : bornes, ordre des chances, compte de tirages."""
    from engine.dsl.base import DslContext

    nr = int(ability_var(ABILITY_ID, AbilityConstantType.nrOfHits.name, is_constant=True) or 0)
    attendues = [int(ability_var(ABILITY_ID, k.name, is_constant=True) or 0)
                 for k in (AbilityConstantType.chance, AbilityConstantType.chance_2,
                           AbilityConstantType.chance_3, AbilityConstantType.chance_4)]
    assert nr >= 1, "kit 1027 sans nrOfHits -- le montage lui-meme est faux"
    # Le test n'aurait aucun pouvoir si les quatre chances etaient toutes >= 100 (tous les jets
    # passeraient sans tirage) ou toutes nulles : on assertionne son propre regime.
    assert all(0 < c < 100 for c in attendues), f"chances non discriminantes : {attendues}"

    # (a) TOUS les jets reussis -> 5 x nrOfHits ; (b) aucun -> 1 x nrOfHits.
    for suite, attendu in (([1, 1, 1, 1], 5 * nr), ([0, 0, 0, 0], 1 * nr)):
        rng = _RngTemoin(suite)
        assert psychic_maelstrom_hits(rng).evaluate(DslContext()) == attendu
        assert rng.chances == attendues, (
            f"ordre/compte des jets faux : {rng.chances} != {attendues}")

    # (c) chaque jet vaut EXACTEMENT +nrOfHits, et l'ordre n'y change rien (le i-eme jet reussi
    #     ajoute la meme chose que le j-eme) -- c'est le `Direct(1)` partage de `formulaTrue`.
    for i in range(4):
        suite = [1 if k == i else 0 for k in range(4)]
        rng = _RngTemoin(suite)
        assert psychic_maelstrom_hits(rng).evaluate(DslContext()) == 2 * nr, f"jet #{i}"
        assert len(rng.chances) == 4, "un `Maybe` doit tirer meme quand un autre a echoue"

    # (d) `rng=None` = branche `!CanUseRandom` du natif (`return 99 < chance`) : aucune des quatre
    #     chances n'atteint 100 -> 1 seul coup, ZERO tirage. C'est le regime de la face DECISION.
    assert psychic_maelstrom_hits(None).evaluate(DslContext()) == 1 * nr


def test_registre_offline():
    """`TARGETING_OPTIONS` + `ABILITY_ATTACK_TYPE` poses, et UNE seule source de masque."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is PsychicMaelstromAbility
    opts = PsychicMaelstromAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, aucun gate n'est applique (degradation permissive)"
    # `<TargetingOptions statics>+0x1a8` = 0x4002, LU dans `TargetingOptions$$.cctor`.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy)
    assert opts.self_cast is False
    assert opts.range is not None and opts.range.use_range_from_config is True
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, (
        "1027 a MIGRE sur sa classe (#490) : deux sources de masque violent le contrat")


def test_damage_bit_exact_live(live_session, rpc, build_runner):
    """Replay-diff repete : deltas HP live == offline, avec un nombre de coups VARIABLE."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    rid = build_runner("49001", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    hits_seen: list = []
    mesures = 0
    for _cast in range(CASTS):
        me = tgt = None
        for _turn in range(10):        # DRIVE a portee (on DEPLACE, cf. doctrine drive-positions)
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _ok(dec):
                pytest.skip("decisionView KO")
            me = next((u for u in (dec.get("units") or [])
                       if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
            if me is None:
                pytest.skip("Sibyll absente ou morte")
            if dec.get("currentPlayer") != me.get("owner"):
                rpc("aiPlayTurn", {"runnerId": rid}, 240)
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            enemies = [u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != me.get("owner")]
            if not enemies:
                pytest.skip("plus d'ennemi vivant")
            tgt = min(enemies, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
            if 1 <= hexgeo.distance(_pos(me), _pos(tgt)) <= RANGE:
                break
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
            tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                     if t.get("col") is not None]
            if tiles:
                tp = _pos(tgt)
                best = min(tiles, key=lambda p: (0 if 1 <= hexgeo.distance(p, tp) <= RANGE else 1,
                                                 hexgeo.distance(p, tp)))
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": me["id"],
                    "to": {"col": best[0], "row": best[1]}}}, 60)
            else:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            tgt = None
        if me is None or tgt is None:
            break

        caster_id, target_id = me["id"], tgt["id"]
        dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        enemies = [u for u in (dec0.get("units") or [])
                   if u.get("alive") and u.get("owner") != me.get("owner")]
        hp0 = {u["id"]: _hp(ob0, u["id"]) for u in enemies}
        state = load_state(dec0, ob0, snap0, board=board)
        if state.get_entity(caster_id) is None:
            pytest.skip("caster absent de l'etat offline")
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        state.rng = rng

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster_id, "targetId": target_id,
            "abilityType": ABILITY}}, 240)
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            break                     # cast refuse (cooldown/geometrie) : on s'arrete, sans skip
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        live = {uid: (hp0[uid] - _hp(ob2, uid))
                for uid in hp0 if hp0.get(uid) is not None and _hp(ob2, uid) is not None}

        runner = Runner(state).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id, target_id, ABILITY))
        diag = runner.ability_handler.last or {}
        # FACE EXECUTER : sans ce booleen, le cast serait un no-op SILENCIEUX (0 degat, 0 erreur).
        assert diag.get("ported") is True, f"1027 non portee : {diag}"
        off = {}
        for uid in live:
            e = state.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is not None:
                off[uid] = hp0[uid] - hc.hp
        assert live == off, f"cast#{_cast} : deltas HP live {live} != offline {off}"

        hits_seen.append(((diag.get("attacks") or [{}])[0] or {}).get("hits"))
        mesures += 1
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    assert mesures >= 3, f"trop peu de casts mesures ({mesures}) -- montage non concluant"
    distinct = sorted({h for h in hits_seen if h is not None})
    # TEMOIN NON DEGENERE : sans deux valeurs de coups distinctes, l'accord ne discriminerait pas
    # un port qui figerait `hits` -- il passerait pour vert. On le refuse explicitement.
    assert len(distinct) >= 2, (
        f"temoin degenere : coups observes {hits_seen} -- l'accord ne prouve pas la formule")
