"""#605 -- `InfernalCannon` (ActiveAbilityType 1209), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline` -- les DEUX donnees obligatoires du registre (`TARGETING_OPTIONS` lu du
    litteral `0x46000040` de la surcharge a SEPT arguments, `ABILITY_ATTACK_TYPE` = 3e argument
    d'`AActiveAbility$$.ctor` = 2 `Others`), et le contrat de DISJONCTION verifie PAR LE CODE ;
  * `test_arbre_offline` -- la FORME : `op_Addition(attaque, AddEffect(Fire))`, dans cet ORDRE, et
    le selecteur `Unique( on-fire + a-pris-du-<damageProfile_2> )`. L'ordre est OBSERVABLE : le feu
    est pose APRES la resolution des cibles, donc il n'elargit pas la volee qui le pose ;
  * `test_profils_distincts_offline` -- le profil TESTE (`damageProfile_2`) n'est PAS le profil
    INFLIGE (`damageProfile`), et le bras assertionne sa PROPRE discriminance : s'ils etaient
    egaux, aucune mesure ne pourrait separer une lecture juste d'une lecture qui deduit l'un de
    l'autre ;
  * `test_cibles_et_degats_live` -- l'oracle. UN ennemi sur trois a pris du Psychic ce tour ; le
    natif ne frappe QUE celui-la, `nrOfHits` fois, et le port doit rendre la MEME liste de cibles
    et la MEME sequence coup par coup. Les deux ennemis intacts sont le TEMOIN NEGATIF : sans eux,
    un port qui frapperait tout le monde passerait.

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268).

MONTAGE. `thousDaemonPrince` << Z'Kar >> est une **MACHINE OF WAR** `lineup` hors du pool et hors
catalogue : `catalog_inject.write_augmented_seed_bc` puis `rl_duel build --seed-bc ... --p-mow`.
⚠ `--explicit-stats` NE convient PAS ici et c'est mesure : la table `units.npc[].stats` du jumeau
`thousNpcMowDaemonPrince` ne porte QUE `StarLevel`/`AbilityLevel`/`ProgressionIndex` -- elle rend
`hp=0 dmg=0 fixedArmor=0`, parce que les stats d'une MoW ne vivent pas la. La voie MoW est la seule
qui amene ce porteur avec son kit.
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
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE. Foyers load-bearing : `abilities/thousandsons.py`
        # (l'arbre), `entities/selectors/units.py` (`UnitsOnTilesWithEffect`, `Filter`, `Unique`),
        # `entities/triggers.py` (`HasTakenDamageOfDamageProfileThisTurn`),
        # `abilities/behaviours/context.py` (le substrat `has_taken_damage_of_profile_this_turn`
        # et `tile_has_effect`), `handler.py` + `attack_type.py` + `targeting.py`.
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1209 InfernalCannon` : l'oracle est le jeu "
              "lui-meme (QUI est frappe -- le selectif `on-fire + a-pris-du-Psychic` --, combien de "
              "coups, et ou le feu est pose). Un changement de build peut faire changer ce fichier "
              "d'avis sans qu'une ligne du port bouge.",
}

import json
import uuid

import pytest

import gameconfig as GC
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.damage_profile_type import DamageProfileType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.thousandsons import (INFERNAL_CANNON_FIRE, INFERNAL_CANNON_ID,
                                                  InfernalCannonAbility, infernal_cannon_tree)
from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"
MOW = "thousDaemonPrince"          # MoW `lineup` HORS pool et HORS catalogue -> catalog_inject
ALLY = "thousSorcerer"             # arme Psychic portee 2 -> c'est LUI qui rend une cible eligible
ENEMIES = "ultraTitus,adeptCanoness,tauMarksman"
CIBLE_ELIGIBLE = "ultraTitus"      # celui que l'allie frappe en Psychic
ABILITY = int(ActiveAbilityType.InfernalCannon)          # 1209
NORMAL_ATTACK = int(ActiveAbilityType.Loki_NormalAttack)  # 69
TUILE_VISEE = (0, 4)               # une tuile VIDE, loin de tout le monde : le feu qu'on y pose ne
                                   # doit rendre PERSONNE eligible -- c'est ce qui isole le volet
                                   # << a pris du damageProfile_2 >> du volet << sur une tuile en feu >>


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _id_de(dv, vis):
    return next((u["id"] for u in _units(dv) if (u.get("visualId") or "") == vis), None)


def _id_mow(dv, vis):
    """Une MACHINE OF WAR ne vit PAS dans `decisionView.units` : elle a sa propre liste `mows`, et
    l'id qui sert de `casterId` a `applyAction` y est `casterId`, pas `id`. Lire `units` rend `None`
    et se lit comme << la MoW n'est pas deployee >> -- une non-mesure prise pour un refus."""
    for m in ((dv or {}).get("mows") or []):
        if (m.get("visualId") or "") == vis:
            return m.get("casterId")
    return None


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _degats_natifs(res):
    """`{target_id: [montants]}` pour les seuls pas `UnitDamaged` portant
    `Active_Ability_Type == 1209` -- resolu PAR NOM de pas. Les autres degats de la cascade (DoT de
    feu, riposte) ne sont PAS de l'ability et n'ont rien a faire dans la confrontation."""
    out: dict = {}
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if t.get("Active_Ability_Type") == ABILITY:
                out.setdefault(int(t["Target_Id"]), []).append(int(t["Amount"]))
    return out


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


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is InfernalCannonAbility, \
        "1209 absente d'ABILITY_CLASSES = NO-OP SILENCIEUX : la decision caste, l'execution ignore"

    opts = InfernalCannonAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # Le LITTERAL du ctor a SEPT arguments -- ni preset copie, ni surcharge PRESET+FLAGS.
    assert int(opts.rules) == 0x46000040
    assert int(opts.rules) == int(TR.TargetIsTile | TR.AllowObscuredTargetByElevation
                                  | TR.AllowObscuredTargetByWalls | TR.AllowNullCasterTile)
    # AUCUN bit dynamique : les deux SEULS symboles du build sont `$$.ctor` et `$$ExecuteBehaviour`.
    assert not (int(opts.rules) & int(TR.TargetMatchesDynamicRule))
    assert opts.self_cast is False
    assert opts.range is not None and opts.range.use_whole_board is True   # statics+0x48
    assert int(opts.force_melee_target) == 1                               # RangedBool.False

    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.Others    # `..ctor(this, &opts, 2)`
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED


def test_profils_distincts_offline():
    """Le profil TESTE et le profil INFLIGE sont DEUX cles distinctes du kit, et ce bras
    assertionne sa PROPRE discriminance : s'ils etaient egaux, aucune mesure ne separerait une
    lecture juste d'une lecture qui deduit l'un de l'autre."""
    consts = (GC.ability(INFERNAL_CANNON_ID) or {}).get("constants") or {}
    inflige, teste = consts.get("damageProfile"), consts.get("damageProfile_2")
    assert inflige and teste
    assert teste != inflige, ("temoin NON DISCRIMINANT : `damageProfile_2` == `damageProfile`, on "
                              "ne pourrait plus distinguer le profil teste du profil inflige")
    assert int(getattr(DamageProfileType, teste)) == int(DamageProfileType.Psychic)
    assert int(getattr(DamageProfileType, inflige)) == int(DamageProfileType.Flame)
    # `GetHits` = `GetNumberConstant(0x2f)` VERBATIM au decompile -- aucun `ExtraHits` de stat.
    assert int(consts["nrOfHits"]) == 3


def test_arbre_offline():
    """La FORME de l'arbre et l'ORDRE de ses deux volets."""
    from engine.entities.selectors.units import Filter, Union, Unique, UnitsOnTilesWithEffect
    from engine.entities.triggers import HasTakenDamageOfDamageProfileThisTurn
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect

    consts = (GC.ability(INFERNAL_CANNON_ID) or {}).get("constants") or {}
    arbre = infernal_cannon_tree(int(DamageProfileType.Psychic), consts["damageProfile"], 16)
    feuilles = _aplatir(arbre)
    noms = [type(f).__name__ for f in feuilles]
    # `op_Addition(atk, addEff)` : la VOLEE part D'ABORD, le feu est pose ENSUITE.
    assert noms == ["AttackWithAttackDamage", "AddEffect"], noms

    atk = feuilles[0]
    assert isinstance(atk, AttackWithAttackDamage)
    assert atk.multi is True and atk.is_melee is False
    assert atk.native_factory == "ability"      # `DSLBehaviors$$AttackWithAbilityDamage`
    assert atk.profile == consts["damageProfile"] == "Flame"     # l'INFLIGE, pas le teste
    assert atk.ability_type == ABILITY

    sel = atk.target_sel
    assert isinstance(sel, Unique), "`Unique` ABSENT : un ennemi a la fois en feu ET touche par le " \
                                    "profil teste serait frappe DEUX fois"
    assert isinstance(sel.source, Union)
    gauche, droite = sel.source.a, sel.source.b
    assert isinstance(gauche, UnitsOnTilesWithEffect)
    assert gauche.effect_type == INFERNAL_CANNON_FIRE == int(EffectType.Fire)
    assert isinstance(droite, Filter)
    assert isinstance(droite.predicate, HasTakenDamageOfDamageProfileThisTurn)
    assert int(droite.predicate.damage_profile) == int(DamageProfileType.Psychic)
    # Le predicat lit `ActiveTarget` -- le slot que `FromTrigger` LIE a chaque candidat.
    assert type(droite.predicate.unit).__name__ == "ActiveTarget"

    feu = feuilles[1]
    assert isinstance(feu, AddEffect)
    assert feu.effect_type == INFERNAL_CANNON_FIRE
    # Surcharge a CINQ arguments : `source = NULL`, `Nullable<turns>` VIDE -> aucune duree ecrite.
    assert feu.source_ref is None and feu.duration_rounds is None and feu.duration_turns is None
    assert type(feu.target_sel).__name__ == "FixedTileIds"      # collapse de `Target@+0x60`


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


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner, tmp_path_factory):
    """Runner `--no-ai` ou Z'Kar est INJECTE au catalogue puis amene par la voie **MoW**."""
    import catalog_inject
    bc = tmp_path_factory.mktemp("seedbc") / ("zkar-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [MOW])
    built = build_runner(SEED, extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--no-ai",
        "--p-mow", MOW, "--p-units", ALLY, "--a-units", ENEMIES,
        # Armure a zero : chaque coup doit etre VISIBLE, sinon un coup absorbe ne se distingue pas
        # d'un coup absent et le compte -- qui EST l'observable -- devient illisible.
        "--armor-target", "0", "--hp-target", "200000",
        "--a-place", "%s:1,2" % CIBLE_ELIGIBLE, "--a-place", "adeptCanoness:3,2",
        "--a-place", "tauMarksman:5,2"], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    zkar = _id_mow(dv, MOW)
    assert zkar is not None, "%s absent de `decisionView.mows` -- injection catalogue + voie MoW " \
                             "KO (mows vus : %r)" % (
                                 MOW, [m.get("visualId") for m in (dv.get("mows") or [])])
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    tuile = next((t["id"] for t in bg["tiles"]
                  if (t.get("col"), t.get("row")) == TUILE_VISEE), None)
    assert tuile is not None, "tuile %r absente du board %s" % (TUILE_VISEE, BOARD)
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq"), "zkar": zkar,
            "tuile": tuile,
            "eligible": _id_de(dv, CIBLE_ELIGIBLE),
            "temoins": [_id_de(dv, v) for v in ("adeptCanoness", "tauMarksman")],
            "allie": _id_de(dv, ALLY)}


def test_cibles_et_degats_live(env, rpc):
    """UN cast, et l'ORACLE sur les deux faces : QUI est frappe, et combien.

    Sequence du montage, dans cet ordre :
      1. deux `endturn` -- 1209 porte `initialCooldownTurns = 1`, elle n'est pas castable au tour 1 ;
      2. l'allie `thousSorcerer` frappe `ultraTitus` de son arme **Psychic** (portee 2) : SEUL cet
         ennemi devient eligible au volet << a pris du damageProfile_2 ce tour >> ;
      3. Z'Kar caste sur une tuile VIDE et lointaine -- donc le volet << sur une tuile en feu >>
         reste vide, et le feu pose n'elargit RIEN (il arrive apres la resolution des cibles).
    Les deux autres ennemis sont le TEMOIN NEGATIF : un port qui frapperait tout le monde
    passerait sans eux."""
    rid, board = env["rid"], env["board"]

    _act(rpc, rid, {"kind": "endturn"}, 120)
    _act(rpc, rid, {"kind": "endturn"}, 120)

    # ⚠ L'ETAT EST CAPTURE **AVANT** L'ATTAQUE PREPARATOIRE, ET LES DEUX MOTEURS LA REJOUENT.
    # `UnitComponent.received_damage_this_turn` -- le dict `ActorStatisticsComponent+0x80` que lit
    # `HasTakenDamageOfDamageProfileThisTurn` -- est un etat INTRA-TOUR que `combatSnapshot` ne
    # publie PAS : cote port il n'existe que si le port a lui-meme joue le degat. Capturer APRES
    # l'attaque native donnerait donc un port aveugle au volet << a pris du damageProfile_2 >>, et
    # son `0 cible` se lirait comme un bug de port alors que c'est un trou de SEEDING. Les deux
    # moteurs partent donc du MEME etat et jouent la MEME sequence : attaque normale, puis cast.
    dv0, st = _etat(rpc, rid, board)
    runner = Runner(st).install_default_handlers(20)

    atk = _act(rpc, rid, {"kind": "ability", "casterId": env["allie"],
                          "targetId": env["eligible"], "abilityType": NORMAL_ATTACK})
    a0 = ((atk or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "l'attaque preparatoire a echoue : %r" % (a0,)
    # L'attaque a-t-elle bien porte du PSYCHIC ? Sans ce controle, un montage ou l'arme melee
    # `Flame` aurait ete choisie rendrait un `0 cible` qui ressemblerait a un bug de port.
    profils = set()
    for a in ((atk or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") == SE.step_id("UnitDamaged"):
                profils.add(int(json.loads(e.get("tags") or "{}").get("DamageProfileType", -1)))
    assert int(DamageProfileType.Psychic) in profils, \
        "l'allie n'a PAS inflige de Psychic (profils vus : %r) -- montage non conforme" % (profils,)

    # LE PORT REJOUE LA MEME ATTAQUE : c'est elle qui alimente son `received_damage_this_turn`.
    runner.apply(AttackUnitMessage(env["allie"], env["eligible"]))
    from engine.runner.components import UnitComponent
    _uc = st.get_entity(env["eligible"]).get_component(UnitComponent)
    assert int(DamageProfileType.Psychic) in (getattr(_uc, "received_damage_this_turn", None) or {}), \
        ("le port n'a PAS enregistre de Psychic sur la cible -- sans cela le volet << a pris du "
         "damageProfile_2 >> serait VIDE des deux cotes et l'accord ne prouverait RIEN")

    res = _act(rpc, rid, {"kind": "ability", "casterId": env["zkar"],
                          "targetId": env["tuile"], "abilityType": ABILITY})
    a1 = ((res or {}).get("actions") or [{}])[0]
    assert a1.get("ok") and a1.get("mutated"), "le natif REFUSE le cast : %r" % (a1,)
    natif = _degats_natifs(res)

    runner.apply(ActiveAbilityMessage(env["zkar"], env["tuile"], ABILITY))
    diag = runner.ability_handler.last or {}
    port: dict = {}
    for a in (diag.get("attacks") or []):
        atkp = a.get("attack") or {}
        port.setdefault(int(a["target"]), list(atkp.get("per_hit") or []))

    hits = int(((GC.ability(INFERNAL_CANNON_ID) or {}).get("constants") or {})["nrOfHits"])
    assert set(natif) == {env["eligible"]}, \
        ("NATIF : cibles %r, attendu le SEUL ennemi ayant pris du Psychic (%r) -- les temoins %r "
         "doivent rester intacts" % (sorted(natif), env["eligible"], env["temoins"]))
    assert len(natif[env["eligible"]]) == hits, \
        "NATIF : %d coup(s), attendu nrOfHits = %d" % (len(natif[env["eligible"]]), hits)
    assert set(diag.get("targets") or []) == set(natif), \
        "PORT cibles %r != NATIF %r" % (sorted(diag.get("targets") or []), sorted(natif))
    assert port == {k: [int(x) for x in v] for k, v in natif.items()}, \
        "sequence coup par coup PORT %r != NATIF %r" % (port, natif)
    # Le feu EST pose sur la tuile visee -- second volet de l'arbre.
    assert diag.get("fire_placed") is True
    assert diag.get("target_tile") == env["tuile"]
