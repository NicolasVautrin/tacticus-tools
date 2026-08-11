"""#893 -- `CrusadeOfWrath` (ActiveAbilityType 1049, `templHelbrecht`), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline` -- les DEUX donnees obligatoires du registre (`TARGETING_OPTIONS` lu du
    litteral `0x400` de la surcharge a SIX parametres -- tranchee par XREFS ENTRANTES, pas par
    l'arite du pseudo-C --, `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor` = 2
    `Others`), et le contrat de DISJONCTION verifie PAR LE CODE ;
  * `test_arbre_offline` -- la FORME : `[A] op_BitwiseAnd ([B] op_Addition [C])`, les DEUX
    `AddStaticStatModifierEffect` sur le MEME selecteur `Friends(SurroundingUnits(CasterTile,
    range) - Caster)`, et le gate `If(Count(sel) > 0)` de l'attaque libre ;
  * `test_temoins_discriminants_offline` -- le bras assertionne sa PROPRE discriminance : les deux
    magnitudes (`extraDmg` / `extraPierceRatio`) et les deux stats (`Attack` / `ExtraPierceMelee`)
    doivent DIFFERER, sinon aucune mesure live ne pourrait separer [A] de [B] ni voir une
    inversion des deux cles de config ;
  * `test_buffs_et_attaque_live` -- l'oracle. QUATRE temoins NEGATIFS dans le MEME runner : le
    CASTER (exclu deux fois par le natif), un allie HORS PORTEE (dist 3), un ennemi DANS la portee
    du buff (dist 2, donc separe par `Friends` et pas par la geometrie), et ce meme ennemi non
    adjacent qui ne doit PAS etre frappe. Sans eux, un port qui bufferait tout le monde passerait ;
  * `test_gate_attaque_sans_ennemi_adjacent_live` -- le regime NEGATIF du gate `If(Count > 0)` :
    aucun ennemi a portee 1 -> AUCUNE attaque, et les DEUX buffs tombent quand meme (donc le `&`
    n'est pas tout-ou-rien).

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268).

MONTAGE. `templHelbrecht` est DEJA au pool (`rl_duel build --list-pool`) : aucune injection
catalogue, aucune greffe, aucun summoner. Les positions sont FORCEES par `--place`/`--a-place` et
les distances hex sont RE-ASSERTIONNEES au runtime contre `boardGraph` -- on ne subit jamais la
geometrie de spawn, et on ne la suppose pas non plus.

⚠ CE QUE CE FICHIER NE DISCRIMINE PAS, et c'est ecrit plutot que tu :
  * le CHOIX de la cible du `PickRandomly(sel, 1)` -- le montage ne laisse qu'UN ennemi adjacent,
    donc la cible est fixee par la geometrie, pas par le tirage. Le bras confronte QUI est frappe,
    mais un `PickRandomly` casse rendrait la meme reponse sur un pool de 1 ;
  * l'EXPIRATION effective des deux effets au bout de 2 rounds -- seul le compteur `remaining`
    publie a la pose est confronte, pas sa decroissance ;
  * le second terme de l'exclusion du caster (`op_Subtraction Caster@+0x48`) PRIS SEUL : sur une
    unite mono-tuile il est redondant avec `includeCenter = 0`, et aucun porteur multi-tuiles ne
    porte 1049.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/hexgeo.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/rl_duel.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE. Foyers load-bearing : `abilities/blacktemplars.py`
        # (l'arbre), `entities/selectors/units.py` (`SurroundingUnits`, `Friends`, `Sub`, `And`,
        # `AdjacentEnemies`, `ValidNormalAttackTargets`), `entities/selectors/geometry.py`
        # (`PickRandomly`), `abilities/behaviours/effects.py` (`AddStaticStatModifierEffect` et
        # `_resolve_duration`), `abilities/behaviours/combat.py` (`UseActiveAbility`),
        # `handler.py` + `attack_type.py` + `targeting.py` (les registres).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1049 CrusadeOfWrath` : l'oracle est le jeu "
              "lui-meme (QUI est buffe -- le caster ne l'est PAS --, de combien, sur quelle stat, "
              "pour combien de tours, et si l'attaque normale gratuite part). Un changement de "
              "build peut faire changer ce fichier d'avis sans qu'une ligne du port bouge.",
}

import json

import pytest

import gameconfig as GC
import hexgeo
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.runner.abilities.blacktemplars import (CRUSADE_OF_WRATH_BUFF_ROUNDS,
                                                   CRUSADE_OF_WRATH_EXTRA_DAMAGE,
                                                   CRUSADE_OF_WRATH_EXTRA_PIERCE,
                                                   CRUSADE_OF_WRATH_ID, CrusadeOfWrathAbility,
                                                   crusade_of_wrath_tree)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

ABILITY = int(ActiveAbilityType.CrusadeOfWrath)          # 1049
BOARD = "MC1_67"
SEED = "893893"

PORTEUR = "templHelbrecht"      # UNIQUE porteur `lineup` de 1049 (les 2 autres sont npc)
ALLIE_PRES = "templSwordBrother"    # dist 1  -> BUFFE
ALLIE_BORD = "astraBullgryn"        # dist 2  -> BUFFE (la BORNE `<= range`, range = 2)
ALLIE_LOIN = "tauMarksman"          # dist 3  -> temoin NEGATIF de portee
ENNEMI_ADJ = "necroWarden"          # dist 1  -> la cible de l'attaque libre
ENNEMI_PRES = "necroSpyder"         # dist 2  -> temoin NEGATIF d'EQUIPE **et** d'ADJACENCE

#: Geometrie FORCEE (board `MC1_67`, 7x9, adjacence `evenq`). Les distances sont RE-CALCULEES au
#: runtime contre `boardGraph` -- ces couples sont un point de depart, pas une hypothese.
POS = {PORTEUR: (3, 4), ALLIE_PRES: (4, 4), ALLIE_BORD: (3, 6), ALLIE_LOIN: (0, 4)}
POS_ENN = {ENNEMI_ADJ: (2, 4), ENNEMI_PRES: (5, 4)}
#: Regime NEGATIF du gate : le MEME montage, l'ennemi adjacent DEPLACE a distance 2.
POS_ENN_SANS_ADJACENT = {ENNEMI_ADJ: (1, 4), ENNEMI_PRES: (5, 4)}

DIST_ATTENDUES = {ALLIE_PRES: 1, ALLIE_BORD: 2, ALLIE_LOIN: 3, ENNEMI_ADJ: 1, ENNEMI_PRES: 2}


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _id_de(dv, vis):
    return next((u["id"] for u in _units(dv) if (u.get("visualId") or "") == vis), None)


def _pos_de(dv, uid):
    u = next((x for x in ((dv or {}).get("units") or []) if x.get("id") == uid), None)
    if u is None:
        return None
    p = u.get("pos") or u.get("position") or {}
    col, row = p.get("col"), p.get("row")
    return None if col is None or row is None else (int(col), int(row))


def _effets(dv, uid, effect_type):
    """Les entrees `decisionView.effects` de `effect_type` portees par `uid` -- GROUND TRUTH (#100).
    ⚠ Ce canal DROPPE les entrees `IsActive == 0` : une absence peut vouloir dire << pose mais
    INERTE >>, jamais << pas pose >>. Aucun des deux effets de 1049 n'a de `CreateActiveCondition`
    (contraste `BloodChalice_ExtraPiercing` 1369, #576) -- s'il en apparaissait une, ce bras
    rougirait, ce qui est le comportement voulu."""
    u = next((x for x in ((dv or {}).get("units") or []) if x.get("id") == uid), None)
    return [e for e in ((u or {}).get("effects") or []) if e.get("effectType") == effect_type]


def _porteurs(dv, effect_type):
    return sorted(u["id"] for u in _units(dv)
                  if any(e.get("effectType") == effect_type for e in (u.get("effects") or [])))


def _source_effet(dv, uid, effect_type):
    """Le `sourceUnitId` de l'entite-effet, tel que `frida/hooks/game/effects.ts` le publie
    (`EC.sourceUnitId`). `None` = pas publie = PAS MESURE."""
    eff = _effets(dv, uid, effect_type)
    return None if not eff else eff[0].get("source")


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


#: Les DEUX cles de tag `UnitStats_*_Modification_Change` que le natif emet pour les deux volets --
#: LUES sur le flux d'evenements du cast, pas devinees. Le nom de stat y est celui de
#: `IdunBattle.Entities.Enum.StatType`, donc il DISCRIMINE `Attack` de `ExtraPierceMelee` : une
#: inversion des deux `statType` du port se verrait ici et nulle part ailleurs.
TAG_MOD = {int(StatType.ATTACK): "UnitStats_Attack_Modification_Change",
           int(StatType.EXTRA_PIERCE_MELEE): "UnitStats_ExtraPierceMelee_Modification_Change"}


def _stat_mods_natifs(res):
    """`{(stat, unite): montant}` -- les modifications de stat ECRITES par le cast, lues sur les pas
    `UnitStatsChanged` de la reponse. C'est l'oracle de MAGNITUDE **et** de STAT : le canal nomme la
    stat, donc il separe [A] de [B]."""
    out: dict = {}
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("kind") != "action":
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            for stat, cle in TAG_MOD.items():
                if cle in t:
                    out[(stat, int(e["entity"]))] = int(t[cle])
    return out


def _duree_effet_native(res, effect_type_name):
    """`{unite: Effect_RemainingTurns}` pour les poses portant `source == effect_type_name` --
    l'oracle de DUREE (`TurnsFromRounds(2)` converti en TOURS par `ConvertRoundsToTurns`)."""
    out: dict = {}
    for a in ((res or {}).get("actions") or []):
        courant = None
        for e in (a.get("events") or []):
            if e.get("kind") == "group":
                courant = e.get("source")
                continue
            if courant != effect_type_name or e.get("kind") != "action":
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Effect_RemainingTurns" in t:
                out[int(e["entity"])] = int(t["Effect_RemainingTurns"])
    return out


def _degats_natifs(res):
    """`{attaquant: {cible: [montants]}}` sur les pas `UnitDamaged` de la reponse du cast.

    ⚠ L'attaque libre de 1049 est une attaque NORMALE : ses evenements portent
    `Active_Ability_Type == 69 Loki_NormalAttack`, PAS `1049` -- les attribuer par l'ability rendrait
    un ensemble VIDE, qui se lirait comme << aucune attaque >> (faute commise a la 1re passe). La cle
    d'attribution est `Attacker_Id`, pas `Source_Id` : ce tag-la n'existe pas sur ce pas."""
    out: dict = {}
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            src, tgt = t.get("Attacker_Id"), t.get("Target_Id")
            if src is None or tgt is None:
                continue
            out.setdefault(int(src), {}).setdefault(int(tgt), []).append(int(t["Amount"]))
    return out


def _profil_attaque_libre(res, attaquant):
    """`(active_ability_type, is_melee)` de l'attaque libre, lus sur ses evenements. L'i2 dit
    << normal MELEE attack >> : ce couple est ce qui le confronte."""
    types, melee = set(), set()
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Attack_Weapon_IsMelee" in t:
                melee.add(int(t["Attack_Weapon_IsMelee"]))
            if e.get("step") == SE.step_id("UnitDamaged") and t.get("Attacker_Id") == attaquant:
                types.add(int(t.get("Active_Ability_Type", -1)))
    return types, melee


def _etat(rpc, rid, board):
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 60)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    assert _ok(s), "dumpRng KO -- MT non calable ; sans lui le degat offline est un faux 0"
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    st.rng = rng
    return dv, st


def _aplatir(noeud) -> list:
    enfants = getattr(noeud, "behaviours", None) or getattr(noeud, "items", None)
    if enfants is None:
        gauche, droite = getattr(noeud, "left", None), getattr(noeud, "right", None)
        if gauche is not None and droite is not None:
            return _aplatir(gauche) + _aplatir(droite)
        return [noeud]
    out: list = []
    for e in enfants:
        out.extend(_aplatir(e))
    return out


def _params_gameconfig():
    """`(range, extra_dmg, extra_pierce)` au niveau 50 et multiplier NEUTRE. Sert UNIQUEMENT au bras
    de discriminance offline (les deux magnitudes doivent differer) -- **jamais** comme valeur
    attendue live : le porteur porte un `AbilityVariablesMultiplierPercentage` != 100 et seul
    `extraDmg` est scale."""
    from engine.entities.effects.magnitude import ability_var
    return (int(ability_var(CRUSADE_OF_WRATH_ID, "range", is_constant=True)),
            int(ability_var(CRUSADE_OF_WRATH_ID, "extraDmg", 50)),
            int(ability_var(CRUSADE_OF_WRATH_ID, "extraPierceRatio", 50)))


def _params_du_port(state, caster_id):
    """`(range, extra_dmg, extra_pierce)` TELS QUE LE PORT LES CALCULE pour CE caster -- l'appel est
    fait sur l'instance d'ability elle-meme, donc niveau d'ability et multiplier de rarete LUS sur
    l'unite. C'est ce qui COUPLE les criteres live au port : muter `_params` (oublier le multiplier,
    inverser les deux cles, lire `range` en variable) fait bouger la valeur attendue et rougir le
    bras. Recopier `277` / `24` ici aurait rendu un bras VERT sur un port casse -- et un bras ROUGE
    sur le port JUSTE, ce qui est arrive a la premiere passe (live 499, gameconfig nu 277 : le
    porteur est a multiplier 180)."""
    return CrusadeOfWrathAbility()._params(state, caster_id)


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is CrusadeOfWrathAbility, \
        "1049 absente d'ABILITY_CLASSES = NO-OP SILENCIEUX : la decision caste, l'execution ignore"

    opts = CrusadeOfWrathAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # Le LITTERAL de la surcharge a SIX parametres -- ni preset copie, ni surcharge PRESET+FLAGS.
    assert int(opts.rules) == 0x400
    assert int(opts.rules) == int(TR.TargetIsFriendly)
    # CONTRE-EXEMPLE LOAD-BEARING : le voisin 1061 `UnbreakableDuty`, MEME forme de ctor et MEME
    # `TargetingRange` statique, porte EN PLUS `CasterIsPossibleTarget`. Recopier son masque aurait
    # ouvert le cast sur le caster -- que l'arbre exclut deux fois.
    assert not (int(opts.rules) & int(TR.CasterIsPossibleTarget))
    assert opts.self_cast is True
    assert opts.range is not None and opts.range.use_range_from_config is True   # statics+0x18
    assert int(opts.force_melee_target) == 1                                     # RangedBool.False

    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.Others   # `..ctor(this, &opts, 2)`
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, \
        "contrat de DISJONCTION rompu : 1049 a DEUX sources de masque"


def test_temoins_discriminants_offline():
    """Ce bras assertionne sa PROPRE discriminance -- il ne mesure rien du port.

    Si `extraDmg == extraPierceRatio`, aucune mesure live ne pourrait separer [A] de [B], ni voir
    une INVERSION des deux cles de config (`8` <-> `0x3f`). Idem pour les deux `StatType`."""
    _rng, dmg, pierce = _params_gameconfig()
    assert dmg > 0 and pierce > 0
    assert dmg != pierce, ("temoin NON DISCRIMINANT : extraDmg == extraPierceRatio, une inversion "
                           "des deux cles de config serait invisible")
    assert int(StatType.ATTACK) != int(StatType.EXTRA_PIERCE_MELEE)
    assert CRUSADE_OF_WRATH_EXTRA_DAMAGE != CRUSADE_OF_WRATH_EXTRA_PIERCE
    # `extraPierceRatio` n'est PAS dans `variablesAffectedByRarityBonus` -> il ne doit PAS bouger
    # avec le multiplier ; `extraDmg` si. C'est une regle de CONFIG, re-derivee, pas une exception.
    affectees = (GC.ability(CRUSADE_OF_WRATH_ID) or {}).get("variablesAffectedByRarityBonus") or []
    assert "extraDmg" in affectees and "extraPierceRatio" not in affectees


def test_arbre_offline():
    """La FORME de l'arbre, ses DEUX selecteurs, et l'ORDRE de ses trois volets."""
    from engine.entities.behaviours import If as IfBehaviour
    from engine.entities.formulas import Count
    from engine.entities.selectors.units import (AdjacentEnemies, And, Friends, Sub,
                                                 SurroundingUnits, ValidNormalAttackTargets)
    from engine.entities.triggers import AmountIsGreaterThanZero
    from engine.entities.unit_selection_type import UnitSelectionType
    from engine.runner.abilities.behaviours.combat import UseActiveAbility
    from engine.runner.abilities.behaviours.effects import AddStaticStatModifierEffect

    rng_range, dmg, pierce = _params_gameconfig()
    arbre = crusade_of_wrath_tree(rng_range, dmg, pierce)
    feuilles = _aplatir(arbre)
    noms = [type(f).__name__ for f in feuilles]
    # `[A] & ([B] + [C])` : les deux buffs D'ABORD, l'attaque libre ENSUITE.
    assert noms == ["AddStaticStatModifierEffect", "AddStaticStatModifierEffect", "If"], noms

    a, b, c = feuilles
    assert isinstance(a, AddStaticStatModifierEffect) and isinstance(b, AddStaticStatModifierEffect)
    assert a.effect_type == CRUSADE_OF_WRATH_EXTRA_DAMAGE == int(EffectType.CrusadeOfWrath_ExtraDamage)
    assert b.effect_type == CRUSADE_OF_WRATH_EXTRA_PIERCE == int(EffectType.CrusadeOfWrath_ExtraPierce)
    assert a.stat_type == int(StatType.ATTACK)                    # statType = 0
    assert b.stat_type == int(StatType.EXTRA_PIERCE_MELEE)        # statType = 0x15 = 21
    assert int(a.amount.evaluate(None)) == dmg
    assert int(b.amount.evaluate(None)) == pierce
    # `TurnsFromRounds(2)` -- le MEME noeud passe aux deux feuilles cote natif.
    assert a.duration_rounds == b.duration_rounds == CRUSADE_OF_WRATH_BUFF_ROUNDS == 2
    assert a.duration_turns is None and b.duration_turns is None

    # Le selecteur de BUFF, terme par terme.
    for feuille in (a, b):
        sel = feuille.unit_sel
        assert isinstance(sel, Friends), type(sel).__name__
        assert type(sel.reference).__name__ == "Owner"            # `of = Owner@+0x30`
        assert int(sel.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
        assert isinstance(sel.inner, Sub), "le `op_Subtraction Caster@+0x48` a disparu"
        assert type(sel.inner.b).__name__ == "Caster"
        autour = sel.inner.a
        assert isinstance(autour, SurroundingUnits)
        assert type(autour.center).__name__ == "CasterTile"       # `origin = CasterTile@+0x50`
        assert int(autour.radius.evaluate(None)) == rng_range == 2
        assert autour.include_center is False, "`includeCenter = 0` : le caster ne se buffe PAS"
        assert int(autour.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)

    # Le gate et le selecteur de l'ATTAQUE LIBRE.
    assert isinstance(c, IfBehaviour)
    assert isinstance(c.cond, AmountIsGreaterThanZero)
    assert isinstance(c.cond.a, Count)
    assert c.otherwise is None, "la branche `else` native est NULLE"
    attaque = c.then
    assert isinstance(attaque, UseActiveAbility)
    assert type(attaque.subject_sel).__name__ == "Owner"          # `caster = Owner@+0x30`
    sel_atk = c.cond.a.selector
    assert isinstance(sel_atk, And)
    assert isinstance(sel_atk.a, ValidNormalAttackTargets)
    assert type(sel_atk.a.unit).__name__ == "CasterTile"          # les DEUX slots = CasterTile
    assert type(sel_atk.a.unit_tile).__name__ == "CasterTile"
    assert isinstance(sel_atk.b, AdjacentEnemies)
    assert type(sel_atk.b.center).__name__ == "Caster"            # `AdjacentEnemies(Caster@+0x48)`
    assert int(sel_atk.b.radius.evaluate(None)) == 1, "aucun rayon natif -> ring-1"
    # Le `PickRandomly(sel, 1)` porte le MEME sous-arbre que le `Count` du gate.
    pick = attaque.targets_sel
    assert type(pick).__name__ == "PickRandomly"
    assert int(pick.amount) == 1
    assert pick.source is sel_atk, "le gate et le tirage doivent porter sur le MEME ensemble"


# ---------------------------------------------------------------------------------- LIVE

def _monte(build_runner, rpc, positions_ennemis, tag):
    extra = ["--board", BOARD, "--no-ai", "--rank", "17",
             "--p-units", ",".join([PORTEUR, ALLIE_PRES, ALLIE_BORD, ALLIE_LOIN]),
             "--a-units", ",".join([ENNEMI_ADJ, ENNEMI_PRES]),
             # Armure a zero + PV enormes : chaque coup de l'attaque libre doit etre VISIBLE, et
             # aucun ennemi ne doit mourir (un cadavre sortirait de `ValidNormalAttackTargets` et
             # rendrait le regime illisible).
             "--armor-target", "0", "--hp-target", "400000"]
    for vis, (col, row) in POS.items():
        extra += ["--place", "%s:%d,%d" % (vis, col, row)]
    for vis, (col, row) in positions_ennemis.items():
        extra += ["--a-place", "%s:%d,%d" % (vis, col, row)]
    built = build_runner(SEED, extra=extra, keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    ids = {v: _id_de(dv, v) for v in list(POS) + list(positions_ennemis)}
    manquants = [v for v, i in ids.items() if i is None]
    assert not manquants, "unites absentes de decisionView (%s) : %r" % (tag, manquants)
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq"), "ids": ids, "dv": dv}


@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    """Le runner NOMINAL : un ennemi ADJACENT, un ennemi a distance 2."""
    return _monte(build_runner, rpc, POS_ENN, "nominal")


@pytest.fixture(scope="module")
def env_sans_adjacent(live_session, rpc, build_runner):
    """Le regime NEGATIF du gate : le MEME montage, AUCUN ennemi a distance 1."""
    return _monte(build_runner, rpc, POS_ENN_SANS_ADJACENT, "sans-adjacent")


def _assert_geometrie(env, rpc, attendues, tag):
    """Les distances hex REELLES, re-calculees contre les positions publiees. Un montage qui
    n'installe pas la geometrie voulue ECHOUE ICI -- il ne rend jamais un verdict sur le port."""
    dv = _vue(rpc, env["rid"])
    centre = _pos_de(dv, env["ids"][PORTEUR])
    assert centre is not None, "position du porteur non publiee"
    vues = {}
    for vis, attendu in attendues.items():
        p = _pos_de(dv, env["ids"][vis])
        assert p is not None, "position de %s non publiee" % vis
        vues[vis] = hexgeo.distance(centre, p)
    assert vues == attendues, ("GEOMETRIE non installee (%s) : vue=%r attendu=%r -- le montage "
                               "n'a pas produit le regime, aucun verdict sur le port" %
                               (tag, vues, attendues))


def test_buffs_et_attaque_live(env, rpc):
    """UN cast, et l'ORACLE sur les trois volets : QUI est buffe (et de combien, sur quelle stat,
    pour combien de tours), et QUI encaisse l'attaque normale gratuite.

    QUATRE temoins NEGATIFS dans le MEME runner : le CASTER, l'allie a distance 3, l'ennemi a
    distance 2 (dans la portee du buff -- c'est `Friends` qui l'ecarte, pas la geometrie), et ce
    meme ennemi non adjacent, qui ne doit pas etre frappe."""
    rid, board, ids = env["rid"], env["board"], env["ids"]
    _assert_geometrie(env, rpc, DIST_ATTENDUES, "nominal")

    dv0, st = _etat(rpc, rid, board)
    runner = Runner(st).install_default_handlers(20)
    hel = ids[PORTEUR]

    # AUCUN des deux effets n'est deja pose : sinon le << apres >> ne prouverait rien.
    for ef in (CRUSADE_OF_WRATH_EXTRA_DAMAGE, CRUSADE_OF_WRATH_EXTRA_PIERCE):
        assert _porteurs(dv0, ef) == [], "effet %d deja present AVANT le cast" % ef

    res = _act(rpc, rid, {"kind": "ability", "casterId": hel, "targetId": hel,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    # ⚠ `mutated` N'EST PAS le critere : il rend **False** sur le regime SANS attaque libre alors
    # que les quatre effets sont bel et bien poses (mesure de la 1re passe). Le critere est
    # `actionConsumed` + les evenements.
    assert a0.get("ok") and a0.get("actionConsumed"), "le natif REFUSE le cast : %r" % (a0,)
    dv1 = _vue(rpc, rid)

    runner.apply(ActiveAbilityMessage(hel, hel, ABILITY))
    diag = runner.ability_handler.last or {}
    assert diag.get("ability") == CRUSADE_OF_WRATH_ID, \
        "le PORT n'a pas execute 1049 (diag=%r) -- no-op silencieux" % (diag,)

    attendus = sorted([ids[ALLIE_PRES], ids[ALLIE_BORD]])
    for ef, nom in ((CRUSADE_OF_WRATH_EXTRA_DAMAGE, "ExtraDamage"),
                    (CRUSADE_OF_WRATH_EXTRA_PIERCE, "ExtraPierce")):
        natif = _porteurs(dv1, ef)
        assert natif == attendus, (
            "NATIF %s : porteurs %r, attendu %r (allie dist 1 + allie dist 2). Temoins qui DOIVENT "
            "rester nus : caster=%d, allie dist 3=%d, ennemi dist 2=%d" %
            (nom, natif, attendus, ids[PORTEUR], ids[ALLIE_LOIN], ids[ENNEMI_PRES]))
        port = sorted(p["unit"] for p in (diag.get("buffs") or []) if p["effect_type"] == ef)
        assert port == natif, "PORT %s porteurs %r != NATIF %r" % (nom, port, natif)

    # MAGNITUDE et STAT : les tags `UnitStats_<Stat>_Modification_Change` du flux d'evenements.
    # La valeur ATTENDUE est celle que le PORT calcule POUR CE CASTER (niveau + multiplier de
    # rarete LUS sur l'unite) -- surtout pas le gameconfig nu.
    _rng, dmg, pierce = _params_du_port(st, hel)
    mods = _stat_mods_natifs(res)
    for ef, attendu_montant, stat, nom in (
            (CRUSADE_OF_WRATH_EXTRA_DAMAGE, dmg, int(StatType.ATTACK), "ExtraDamage"),
            (CRUSADE_OF_WRATH_EXTRA_PIERCE, pierce, int(StatType.EXTRA_PIERCE_MELEE), "ExtraPierce")):
        port_montants = sorted(p["amount"] for p in (diag.get("buffs") or [])
                               if p["effect_type"] == ef)
        assert port_montants == [attendu_montant] * len(attendus), \
            "PORT %s montants %r, attendu %r" % (nom, port_montants, attendu_montant)
        for uid in attendus:
            assert (stat, uid) in mods, (
                "NATIF %s : aucune modification de la stat %d sur u%d (mods vus : %r) -- une "
                "INVERSION des deux statType du port se verrait exactement ici" %
                (nom, stat, uid, sorted(mods)))
            assert mods[(stat, uid)] == attendu_montant, \
                "NATIF %s u%d : +%d, PORT +%d" % (nom, uid, mods[(stat, uid)], attendu_montant)
            assert len(_effets(dv1, uid, ef)) == 1, "NATIF %s : instances multiples sur u%d" % (nom, uid)

    # SOURCE DE L'ENTITE-EFFET -- residu NOMME `#893-r2`. Ce bras GELE la mesure NATIVE, il ne juge
    # pas le port : `DSLBehaviors$$AddStaticStatModifierEffect` passe `source = **null**` a
    # `AddStatModifierEffectBehaviour$$.ctor`, et `...$$Execute` retombe alors sur la CIBLE
    # (`lVar9 = <cible courante>; if (source != 0) lVar9 = <source evaluee>;`). Le port, lui, passe
    # `source = le CASTER` dans son foyer PARTAGE `AddStaticStatModifierEffect.execute`. Aucune
    # consequence mesuree ici (montant, stat, duree et porteurs concordent tous), mais l'ecart est
    # REEL et il touche au moins 1049 / 1175 / 1222 / 1106 -- d'ou un residu plutot qu'une retouche
    # de feuille partagee dans une tranche d'ability.
    for ef, nom in ((CRUSADE_OF_WRATH_EXTRA_DAMAGE, "ExtraDamage"),
                    (CRUSADE_OF_WRATH_EXTRA_PIERCE, "ExtraPierce")):
        for uid in attendus:
            src = _source_effet(dv1, uid, ef)
            if src is not None:
                assert int(src) == uid and int(src) != hel, (
                    "NATIF %s u%d : sourceUnitId=%r -- la mesure de #893-r2 disait CIBLE (%d), pas "
                    "CASTER (%d). Si ce bras rougit, c'est le NATIF qui a change, pas le port." %
                    (nom, uid, src, uid, hel))

    # DUREE : `TurnsFromRounds(2)` converti en TOURS par `ConvertRoundsToTurns`.
    from engine.runner.abilities.behaviours.effects import _resolve_duration
    attendu_tours = int(_resolve_duration(st, CRUSADE_OF_WRATH_BUFF_ROUNDS, None))
    for ef, nom in ((CRUSADE_OF_WRATH_EXTRA_DAMAGE, EffectType.CrusadeOfWrath_ExtraDamage.name),
                    (CRUSADE_OF_WRATH_EXTRA_PIERCE, EffectType.CrusadeOfWrath_ExtraPierce.name)):
        durees = _duree_effet_native(res, nom)
        assert durees, "NATIF %s : aucune duree publiee" % nom
        assert set(durees) == set(attendus), \
            "NATIF %s : durees posees sur %r, attendu %r" % (nom, sorted(durees), attendus)
        assert set(durees.values()) == {attendu_tours}, \
            ("NATIF %s : remaining=%r tours, PORT (TurnsFromRounds(%d)) = %d" %
             (nom, sorted(set(durees.values())), CRUSADE_OF_WRATH_BUFF_ROUNDS, attendu_tours))

    # L'ATTAQUE LIBRE : le porteur frappe l'ennemi ADJACENT, et LUI SEUL.
    degats = _degats_natifs(res)
    par_helbrecht = degats.get(hel) or {}
    assert set(par_helbrecht) == {ids[ENNEMI_ADJ]}, (
        "NATIF attaque libre : cibles %r, attendu le SEUL ennemi ADJACENT (u%d). L'ennemi a "
        "distance 2 (u%d) est le temoin d'ADJACENCE." %
        (sorted(par_helbrecht), ids[ENNEMI_ADJ], ids[ENNEMI_PRES]))
    atk = diag.get("attack") or {}
    assert atk, "PORT : aucune attaque libre emise alors que le natif en a portee une"
    assert int(atk.get("target")) == ids[ENNEMI_ADJ], \
        "PORT cible %r != NATIF u%d" % (atk.get("target"), ids[ENNEMI_ADJ])
    per_hit = [int(x) for x in ((atk.get("attack") or {}).get("per_hit") or [])]
    natif_hits = [int(x) for x in par_helbrecht[ids[ENNEMI_ADJ]]]
    assert per_hit == natif_hits, \
        "sequence coup par coup PORT %r != NATIF %r" % (per_hit, natif_hits)
    # C'est bien l'attaque NORMALE (`UnitNormalAttackType(Owner)`), et son arme est celle de MELEE
    # -- « performs a normal MELEE attack » de l'i2. Le port dispatche `AttackDamageOperation`, qui
    # resout l'arme PAR LA DISTANCE : les deux doivent conclure pareil a portee 1.
    types, melee = _profil_attaque_libre(res, hel)
    assert types == {int(ActiveAbilityType.Loki_NormalAttack)}, \
        "NATIF : l'attaque libre porte Active_Ability_Type %r, attendu Loki_NormalAttack" % (types,)
    assert melee == {1}, "NATIF : arme de l'attaque libre non-melee (%r)" % (melee,)
    assert (atk.get("attack") or {}).get("ranged") in (False, 0, None), \
        "PORT : l'attaque libre a ete resolue en RANGED (%r)" % ((atk.get("attack") or {}).get("ranged"),)


def test_gate_attaque_sans_ennemi_adjacent_live(env_sans_adjacent, rpc):
    """Le regime NEGATIF du gate `If(AmountIsGreaterThanZero(Count(sel)))` : AUCUN ennemi a
    distance 1 -> AUCUNE attaque, ni cote natif ni cote port. Et les DEUX buffs tombent quand meme
    -- donc l'`op_BitwiseAnd` n'est pas tout-ou-rien."""
    env = env_sans_adjacent
    rid, board, ids = env["rid"], env["board"], env["ids"]
    _assert_geometrie(env, rpc, dict(DIST_ATTENDUES, **{ENNEMI_ADJ: 2}), "sans-adjacent")

    _dv0, st = _etat(rpc, rid, board)
    runner = Runner(st).install_default_handlers(20)
    hel = ids[PORTEUR]

    res = _act(rpc, rid, {"kind": "ability", "casterId": hel, "targetId": hel,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    # ⚠ MESURE : sur CE regime le natif rend `mutated: False` alors que les QUATRE effets sont
    # poses. `mutated` ne voit pas une pose d'effet -- `actionConsumed` et les evenements, si.
    assert a0.get("ok") and a0.get("actionConsumed"), "le natif REFUSE le cast : %r" % (a0,)
    assert _stat_mods_natifs(res), "aucune modification de stat : le cast n'a rien fait"
    dv1 = _vue(rpc, rid)

    runner.apply(ActiveAbilityMessage(hel, hel, ABILITY))
    diag = runner.ability_handler.last or {}

    assert (_degats_natifs(res).get(hel) or {}) == {}, \
        "NATIF : une attaque est partie sans ennemi ADJACENT -- le gate ne mord pas"
    assert not diag.get("attack"), "PORT : une attaque est partie sans ennemi ADJACENT"

    attendus = sorted([ids[ALLIE_PRES], ids[ALLIE_BORD]])
    for ef, nom in ((CRUSADE_OF_WRATH_EXTRA_DAMAGE, "ExtraDamage"),
                    (CRUSADE_OF_WRATH_EXTRA_PIERCE, "ExtraPierce")):
        assert _porteurs(dv1, ef) == attendus, \
            "NATIF %s : les buffs doivent tomber MEME sans attaque libre" % nom
        port = sorted(p["unit"] for p in (diag.get("buffs") or []) if p["effect_type"] == ef)
        assert port == attendus, "PORT %s porteurs %r != %r" % (nom, port, attendus)

