"""CLIQUET LIVE #1049 -- les deux passifs de SUMMON portes par la tranche, confrontes au NATIF.

  * `RedThirst` (1249) -> effet `RedThirst_ExtraDamageAndHit` (1322) : `+extraDmg` de degat des
    que `HealthPct(Owner) <= healthPct`, `+extraHit` coup EN PLUS quand le porteur CHARGE.
  * `CursedOfTheWalkingPox` (1072) : chaque kill d'un ennemi non-mecanique invoque un CLONE du
    porteur sur l'hex du mort.

Les DEUX observables sont DISCRETS -- un NOMBRE de coups, un NOMBRE d'unites posees : un ecart ne
peut etre ni absorbe ni compense par un regime d'armure, de percage ou de crit. Chaque bras
confronte le live au rejeu offline BIT-EXACT, et porte sa contre-epreuve.

PORTEURS -- deux montages DIFFERENTS, et le choix de chacun est une mesure :

  * `CursedOfTheWalkingPox` : le JUMEAU NPC `deathNpc1Poxwalker` (meme `visualId`, meme
    `passiveAbilities`, meme arme que le summon `deathPoxwalker`), monte par `--explicit-stats`
    (chemin de stats NATIF des npc, #419-r1-tr12-r2). On PILOTE donc le porteur au lieu de
    l'observer -- tout le montage « un summon ne se commande pas » (#291) tombe.
  * `RedThirst` : GREFFE sur un HERO DU POOL (`case-92` SS5bis, recours 3), PAS le jumeau npc.
    ⚠ MESURE du 2026-08-14 : le `combatSnapshot.unitConfig` d'un npc monte par `--explicit-stats`
    rend `{"passiveAbilityLevel": 1, "abilityVariablesMultiplier": 100}` alors que le canal
    `unitAbilityStates` rend `(65, 200)` pour la MEME entite. `snapshot.py::
    _ability_state_with_channel` ne comble QUE le trou (`passive_level` falsy), et ce `1` est
    truthy -> l'offline lirait `extraDmg[1] = 6` la ou le natif lit `extraDmg[65] x 200 %`. C'est
    un artefact du MONTAGE (une unite INVOQUEE, elle, n'a AUCUN `unitConfig`, donc le canal gagne),
    et il ferait accuser le port. Residu `#1049-r1`.
    La greffe est LEGITIME ici parce que les trois corps natifs de 1322 ne lisent NI stat NI trait
    du caster -- seulement la config d'ability et le RATIO DE PV du porteur.

MESURE DE REFERENCE (`probe_1049_red_thirst_walking_pox.py`, MC1_67 / seed 777, `astraBullgryn`
greffe, arme 4 coups Physical) :

    CHARGE_BLESSE  live n=5 [5281, 3132, 4010, 4016, 3486]  == offline, bit-exact
    NOSTEP_BLESSE  live n=4 [5281, 3132, 4010, 4016]        == offline, bit-exact
    CHARGE_PLEIN   live n=4 [4682, 2533, 3411, 3417]        == offline, bit-exact
    controle (1322 RETIRE, tous regimes)  n=4 [4682, 2533, 3411, 3417]

soit `+599 = extraDmg[50] x 180 %` par coup DES QUE les PV sont sous le seuil (charge ou non), et
`+1 coup` SEULEMENT en charge.

    POX POSITIF    live u100 `deathPoxwalker` (6,8) hp=6555 parent=81 | offline idem
    POX MECANIQUE  live 0 spawn | offline 0 spawn

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import (CHARGE, NO_STEP,                       # noqa: E402,F401  (fixture)
                            charge_regime, _seed_rng)

from engine.runner.components import (HealthComponent, PositionComponent,   # noqa: E402
                                      UnitComponent)
from engine.runner.messages import AttackUnitMessage                        # noqa: E402
from engine.runner.runner import Runner                                     # noqa: E402
from engine.runner.snapshot import load_state                               # noqa: E402

#: Ce qui doit changer pour que ce fichier puisse changer de verdict. LARGE A DESSEIN : il
#: confronte le NATIF, donc il depend du BUILD (les trois corps de 1322 et les deux de 1072 vivent
#: dans le binaire) et de tout le harnais qui monte la bataille -- pas seulement des trois modules
#: de port que la tranche a ecrits.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/triggers/loki/cursed_of_the_walking_pox.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/tests/conftest.py",
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Confrontation LIVE des deux passifs #1049 sur CINQ runners (3 regimes RedThirst, "
        "2 bras Poxwalker, + 2 generalisations board/seed). Depend du BUILD (les corps natifs de "
        "1322 et 1072), du harnais de montage (`_charge_regime`, `rl_duel --unit-stat` pour la "
        "greffe, `catalog_inject --explicit-stats` pour le porteur npc) et de toute la chaine de "
        "rejeu offline (`snapshot.load_state`, `damage_model`, `battle_query.is_charging`)."),
}

#: Hote de greffe : 4 coups Physical MELEE. Son passif d'origine (`AvalancheOfMuscle`, un
#: extra-degat lui aussi gate `IsCharging`) est REMPLACE par la greffe -- ce qui evite justement
#: qu'il confonde le regime de charge.
GRAFT_HOST = "astraBullgryn"
RED_THIRST_ID = 1249                     # `TriggeredAbilityType.RedThirst`
EFFECT_NAME = "RedThirst_ExtraDamageAndHit"
#: `--hp-player 120000` (fixture) force `Health` ET `RemainingHealth` ; `--unit-stat` s'applique
#: APRES et rabaisse le seul `RemainingHealth` -> 50000 / 120000 = 41,7 % <= `healthPct` (50).
HOST_HP_WOUNDED = 50000

POXWALKER_NPC = "deathNpc1Poxwalker:45"
POXWALKER_VIS = "deathPoxwalker"
#: 2e ennemi -- TEMOIN DE CONTINUATION, jamais attaque. MESURE : avec un seul ennemi, le kill
#: termine le match et le `decisionView` d'apres rend `units: []` -> le spawn, pourtant EMIS par le
#: natif dans les events du meme `applyAction`, devient INOBSERVABLE et le bras accuse le port.
POX_FILLER = "worldJakhal"


def _graft(remaining=None):
    fields = "PassiveAbilities=[%d]" % RED_THIRST_ID
    if remaining is not None:
        fields += ",RemainingHealth=%d" % remaining
    return ["--unit-stat", "%s:%s" % (GRAFT_HOST, fields)]


# ------------------------------------------------------------------ fixtures RedThirst

@pytest.fixture(scope="module")
def rt_blesse(charge_regime):
    return charge_regime(p_units=GRAFT_HOST, a_units="necroWarden,necroOverlord",
                         extra=_graft(HOST_HP_WOUNDED))


@pytest.fixture(scope="module")
def rt_plein(charge_regime):
    return charge_regime(p_units=GRAFT_HOST, a_units="necroWarden,necroOverlord",
                         extra=_graft(None))


@pytest.fixture(scope="module")
def rt_blesse_alt(charge_regime):
    """GENERALISATION : meme invariant, AUTRE board, AUTRE seed, AUTRES cibles."""
    return charge_regime(p_units=GRAFT_HOST, a_units="orksNob,tyranTyrantGuard",
                         seed="31337", board="C1_25", extra=_graft(HOST_HP_WOUNDED))


def _replay_without_effect(h, rec):
    """CONTRE-EPREUVE : meme rejeu, l'instance 1322 RETIREE. Deux offline identiques = scenario
    NON discriminant, donc verdict vide."""
    st = h.offline_state(rec)
    if st.effects is not None:
        for uid, lst in list(st.effects.by_unit.items()):
            st.effects.by_unit[uid] = [e for e in lst if getattr(e, "name", None) != EFFECT_NAME]
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
    return list((runner.damage_handler.last or {}).get("per_hit") or [])


def _replay_with_effect_forced(h, rec, ability_level, mult):
    """Rejeu du MEME coup avec l'instance 1322 MATERIALISEE DE FORCE sur le caster.

    ⚠ POURQUOI CE BRAS EXISTE -- une MESURE, pas une precaution. Le mutant « `is_active` rend
    toujours True » laissait `test_redthirst_plein_active_condition_ferme` VERT : sur l'hote de
    GREFFE, l'instance n'existe tout simplement PAS a PV pleins (le canal `decisionView.effects`
    est ACTIF-ONLY, et le seed `ABILITY_INIT_OWNER_EFFECTS` lit le kit **gameconfig** du
    `visualId`, ou la greffe -- qui vit dans la `BC` -- n'apparait pas). Le bras prouvait donc
    « live == offline » sans rien dire de la CONDITION. En posant l'instance a la main, on met le
    port dans l'etat du VRAI porteur (`bloodSmnIntercessor`, dont le kit gameconfig porte
    `RedThirst`, donc que le seed materialise) : c'est LA que l'active-condition est load-bearing."""
    from engine.runner.operations.spawn import _materialize_owner_effect
    st = h.offline_state(rec)
    assert _materialize_owner_effect(st, rec["caster"], EFFECT_NAME, mult,
                                     ability_level=ability_level), \
        "l'instance 1322 etait DEJA la : le bras ne mesure pas ce qu'il croit"
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
    return list((runner.damage_handler.last or {}).get("per_hit") or [])


def _run(h, regime):
    rec = h.run(caster_visual=GRAFT_HOST, regime=regime)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    return rec, h.replay_offline(rec), _replay_without_effect(h, rec)


def _effet_present(h, rec, off):
    return [e for e in (off["state"].effects.by_unit.get(rec["caster"]) or [])
            if getattr(e, "name", None) == EFFECT_NAME]


# ------------------------------------------------------------------ RedThirst : les 3 regimes

def test_redthirst_charge_blesse_les_deux_canaux(rt_blesse):
    """PV sous le seuil ET charge : `+extraDmg` par coup ET `+extraHit` coup. Le natif rend UN
    COUP DE PLUS que le controle, et chacun des coups communs vaut controle + `extraDmg`."""
    rec, off, ctl = _run(rt_blesse, CHARGE)
    assert _effet_present(rt_blesse, rec, off), "1322 non materialise offline : verdict vide"
    assert off["charged"], "le pas n'a pas charge la cible : le regime ne dit pas ce qu'il promet"
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE+BLESSE : live n=%d %s | offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
    # canal COUPS : EXACTEMENT un coup de plus que sans l'effet.
    assert len(rec["live_per_hit"]) == len(ctl) + 1, (
        "le +extraHit de charge ne vaut pas +1 coup : live n=%d, controle n=%d"
        % (len(rec["live_per_hit"]), len(ctl)))
    # canal DEGAT : le MEME increment sur chaque coup commun, et il est NON NUL.
    deltas = {a - b for a, b in zip(rec["live_per_hit"], ctl)}
    assert len(deltas) == 1 and deltas.pop() > 0, (
        "increment de degat non constant/nul : live=%s controle=%s" % (rec["live_per_hit"], ctl))


def test_redthirst_nostep_blesse_degat_sans_charge(rt_blesse):
    """LE REGIME DISCRIMINANT DU GATE. La PROSE i2 rattache « when charging » aux DEUX termes ; le
    decompile ne le met que sur le canal COUPS. Sans pas : le nombre de coups est celui du
    controle, mais chaque coup porte deja le `+extraDmg`."""
    rec, off, ctl = _run(rt_blesse, NO_STEP)
    assert _effet_present(rt_blesse, rec, off), "1322 non materialise offline : verdict vide"
    assert not off["charged"], "regime NO_STEP mais la cible est chargee : montage invalide"
    assert off["per_hit"] == rec["live_per_hit"], (
        "NO_STEP+BLESSE : live n=%d %s | offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
    assert len(rec["live_per_hit"]) == len(ctl), (
        "hors charge le natif ne donne PAS de coup en plus : live n=%d, controle n=%d"
        % (len(rec["live_per_hit"]), len(ctl)))
    deltas = {a - b for a, b in zip(rec["live_per_hit"], ctl)}
    assert len(deltas) == 1 and deltas.pop() > 0, (
        "le canal DEGAT devrait mordre SANS charge : live=%s controle=%s" % (rec["live_per_hit"], ctl))


def test_redthirst_plein_active_condition_ferme(rt_plein):
    """PV pleins : l'active-condition est FAUSSE, donc AUCUN des deux canaux ne mord -- meme en
    charge. Le natif le DIT deux fois : il rend les valeurs du controle, et il publie l'effet avec
    `active: false` (mesure `includeInactive`).

    LE 3e BRAS EST CELUI QUI GARDE LA CONDITION, et il a ete ajoute parce que le mutant l'a exige :
    les deux premieres assertions restaient VERTES avec un `is_active` cable a `True`, l'instance
    n'existant pas sur l'hote de greffe (cf. `_replay_with_effect_forced`). Une garde qu'on ne sait
    pas faire echouer ne garde rien."""
    rec, off, ctl = _run(rt_plein, CHARGE)
    assert off["charged"], "le pas n'a pas charge la cible : le regime ne dit pas ce qu'il promet"
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE+PLEIN : live n=%d %s | offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == ctl, (
        "a PV pleins le port applique quand meme 1322 : off=%s controle=%s" % (off["per_hit"], ctl))
    # 3e bras : l'instance EST la (comme sur le vrai porteur), et elle doit rester INERTE.
    force = _replay_with_effect_forced(rt_plein, rec, ability_level=50, mult=180)
    assert force == rec["live_per_hit"], (
        "1322 MATERIALISE a PV pleins contribue quand meme : force=%s | live=%s"
        % (force, rec["live_per_hit"]))


def test_redthirst_generalisation_autre_board_autre_seed(rt_blesse_alt):
    """Un resultat obtenu sur UN SEUL board n'en est pas un des que la mecanique touche a la
    geometrie (`runner.md` SS2). Meme invariant, `C1_25` / 31337, autres cibles."""
    rec, off, ctl = _run(rt_blesse_alt, CHARGE)
    assert _effet_present(rt_blesse_alt, rec, off), "1322 non materialise offline : verdict vide"
    assert off["per_hit"] == rec["live_per_hit"], (
        "GENERALISATION : live n=%d %s | offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
    assert len(rec["live_per_hit"]) == len(ctl) + 1


# ------------------------------------------------------------------ CursedOfTheWalkingPox

@pytest.fixture(scope="module")
def pox_positif(charge_regime):
    return charge_regime(p_units=POXWALKER_NPC, a_units="orksNob,%s" % POX_FILLER,
                         extra=["--explicit-stats", POXWALKER_NPC, "--hp-target", "1"])


@pytest.fixture(scope="module")
def pox_mecanique(charge_regime):
    return charge_regime(p_units=POXWALKER_NPC, a_units="necroWarden,%s" % POX_FILLER,
                         extra=["--explicit-stats", POXWALKER_NPC, "--hp-target", "1"])


@pytest.fixture(scope="module")
def pox_positif_alt(charge_regime):
    """GENERALISATION : meme invariant, AUTRE board, AUTRE seed."""
    return charge_regime(p_units=POXWALKER_NPC, a_units="orksNob,%s" % POX_FILLER,
                         seed="31337", board="C1_25",
                         extra=["--explicit-stats", POXWALKER_NPC, "--hp-target", "1"])


def _pox_kill(h, victim_vis):
    """Amene le porteur AU CONTACT de `victim_vis`, SNAPSHOTe, TUE en live, puis rejoue le MEME
    coup offline. Rend `(live_new, off_new, tuile_victime, parent_id)`.

    `live_new` / `off_new` = les unites APPARUES, sous la forme `(visualId, (col,row), hp, parent)`.
    """
    dv = h.dview()
    me = h.by_visual(POXWALKER_VIS, dv)
    tgt = h.by_visual(victim_vis, dv)
    if me is None or tgt is None:
        pytest.skip("porteur ou victime absents du decisionView")
    h.my_player = me.get("owner")
    if h.reach_my_turn(force_cycle=True) is None:
        pytest.skip("tour du porteur non atteint")
    tpos = (tgt["pos"]["col"], tgt["pos"]["row"])
    free = h.free_tiles(tpos, 1, exclude=(tpos,))
    if not free or not h.place(me["id"], free[0]):
        pytest.skip("aucune tuile libre adjacente a la victime")
    if h.reach_my_turn(force_cycle=True) is None:
        pytest.skip("tour du porteur non atteint (apres pose)")
    snap = h.snapshot()
    before = {u["id"] for u in (h.dview().get("units") or [])}
    atype = h.normal_attack_type(me["id"])
    if atype is None:
        pytest.skip("attaque normale du porteur non resolue")
    h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
        "abilityType": int(atype)}}, 60)
    dv2 = h.dview()
    if any(u["id"] == tgt["id"] for u in h.alive(dv2)):
        pytest.skip("la victime a survecu : le vecteur On(PostUnitKill) n'a pas eu lieu")
    live_new = [(u.get("visualId"), ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row")),
                 u.get("hp"), u.get("parentId"))
                for u in (dv2.get("units") or []) if u["id"] not in before]

    st = load_state(snap["dv"], snap["ob"], snap["snap"], board=h.board)
    dump = snap.get("rng")
    if isinstance(dump, dict) and dump.get("mt"):
        st.rng = _seed_rng(dump)                      # MEME etat de PRNG que le coup live
    off_before = set(st.entities.keys())
    Runner(st).install_default_handlers(20).apply(
        AttackUnitMessage(attacker_id=me["id"], target_id=tgt["id"]))
    off_new = []
    for eid in sorted(set(st.entities.keys()) - off_before):
        ent = st.get_entity(eid)
        uc, pc, hc = (ent.get_component(UnitComponent), ent.get_component(PositionComponent),
                      ent.get_component(HealthComponent))
        off_new.append((getattr(uc, "visual_id", None),
                        (pc.col, pc.row) if pc is not None else None,
                        getattr(hc, "hp", None), getattr(uc, "parent_id", None)))
    return live_new, off_new, tpos, me["id"]


def test_pox_kill_non_mecanique_invoque_un_clone(pox_positif):
    """Le natif pose UN `deathPoxwalker` SUR L'HEX du mort, aux PV du PARENT (`CopyOwner`), avec le
    porteur pour parent (`Spawn(Owner, ...)`). Le port en pose exactement autant, au meme endroit,
    aux memes PV.

    ⚠ Les PV sont l'observable qui separe `CopyOwner` de `WithStatsFromConfig` : l'ability n'a
    AUCUNE variable `summonHp`, donc un port qui aurait pris l'autre chemin poserait un clone a
    0 PV -- vivant, mais faux, et sans la moindre erreur."""
    live_new, off_new, tpos, parent = _pox_kill(pox_positif, "orksNob")
    live_pox = [x for x in live_new if x[0] == POXWALKER_VIS]
    off_pox = [x for x in off_new if x[0] == POXWALKER_VIS]
    assert len(live_pox) == 1, "le natif n'a pas invoque : live_new=%s" % (live_new,)
    assert len(off_pox) == len(live_pox), (
        "nombre de spawns : live=%d offline=%d (%s vs %s)"
        % (len(live_pox), len(off_pox), live_new, off_new))
    assert off_pox[0][1] == tuple(tpos) == live_pox[0][1], (
        "tuile du clone : live=%s offline=%s attendu=%s" % (live_pox[0][1], off_pox[0][1], tpos))
    assert off_pox[0][2] == live_pox[0][2], (
        "PV du clone (CopyOwner) : live=%s offline=%s" % (live_pox[0][2], off_pox[0][2]))
    assert off_pox[0][3] == parent == live_pox[0][3], (
        "parent du clone : live=%s offline=%s attendu=u%s"
        % (live_pox[0][3], off_pox[0][3], parent))


def test_pox_kill_mecanique_n_invoque_rien(pox_mecanique):
    """CONTRE-EPREUVE du gate `NOT HasTrait(Target, 0x5 = Mechanical)` (i2 : « an enemy
    **non-Mechanical** unit »). Meme porteur, meme geometrie, meme kill -- une victime `Mechanical`
    ne produit AUCUN spawn, ni live ni offline."""
    live_new, off_new, _tpos, _parent = _pox_kill(pox_mecanique, "necroWarden")
    assert [x for x in live_new if x[0] == POXWALKER_VIS] == [], (
        "le natif a invoque sur une victime Mechanical : %s" % (live_new,))
    assert [x for x in off_new if x[0] == POXWALKER_VIS] == [], (
        "le port invoque sur une victime Mechanical : %s" % (off_new,))


def test_pox_generalisation_autre_board_autre_seed(pox_positif_alt):
    """Le placement du clone est board-dependant (`First(CanAddUnit(TargetTiles))`) : un resultat
    sur UN SEUL board n'en est pas un."""
    live_new, off_new, tpos, parent = _pox_kill(pox_positif_alt, "orksNob")
    live_pox = [x for x in live_new if x[0] == POXWALKER_VIS]
    off_pox = [x for x in off_new if x[0] == POXWALKER_VIS]
    assert len(live_pox) == 1 and len(off_pox) == 1, (
        "GENERALISATION : live=%s offline=%s" % (live_new, off_new))
    assert off_pox[0][1] == tuple(tpos) == live_pox[0][1]
    assert off_pox[0][2] == live_pox[0][2]
