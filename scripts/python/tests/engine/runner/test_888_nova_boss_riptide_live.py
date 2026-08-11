"""CONFRONT LIVE des DEUX actives de cast du boss de guilde `tauBossRiptide` -- #888.

`1194 NovaShield` (tile-target) et `1192 NovaBoost` (self-cast). Ce que ce fichier GARDE, et
pourquoi chaque garde existe :

  * **le cast NE FRAPPE PAS.** L'audit `combat-ability-coverage` classe les deux
    `DAMAGE(Particle)` -- colonne derivee du `damageProfile` du KIT, pas du behaviour. Les deux
    `ExecuteBehaviour` ne portent AUCUN noeud d'attaque : le degat appartient aux TRIGGERED de
    phase 2 (`...Triggered.Loki.NovaShield_AttackAbility`, `NovaBoost_AttackAbility`), NON portees.
    Sans cette garde, un futur port « qui frappe parce que le kit annonce un profil » passerait.
  * **le filtre `NOT IsTrenchTile` de la zone marquee**, et il n'est observable QUE si la zone
    contient une tuile `Trench`. Le board du boss (`GB_Riptide_01`) en porte 6, le board generique
    `MC1_67` en porte **zero** : sur ce dernier, un port SANS le filtre serait INDISTINGUABLE. La
    garde exige donc que le CONTRE-MODELE (« sans filtre ») DIFFERE du natif -- un accord sur une
    zone sans trench serait une LIMITE, pas une confirmation.
  * **la SURCHARGE d'`AddEffect`, qui n'est lisible qu'a l'ARITE.** 1194 appelle la 5-args (aucun
    selecteur source) -> `AddEffectBehaviour$$Execute` prend `src = <cible courante>`, donc chaque
    TUILE marquee est SA PROPRE source ; 1192 appelle la 6-args avec `Caster@+0x48`. Le nom de la
    fonction est identique dans les deux cas, et `decisionView` ne publie pas la source -> la
    garde lit la CASCADE du cast natif ET les instances du port.
  * **la MAGNITUDE du bouclier**, qui a trouve un vrai bug : le natif indexe l'`AbilityState`
    PER-ABILITY (`level 55, multiplier 200`), pas le canal global `ctx.active_ability_level`
    (`0 / 100` sur un npc). Ecart mesure : `shieldHp` 100 contre 13686.
  * **l'EMPREINTE du caster**, via un temoin NATIF plutot qu'un canal : `1193 NovaCharge` porte
    `CasterHas7Tiles` (bit 37) et `TargetingQuery$$GetInvalidCasterReason` refuse
    `GetFeetCount(caster) != 7`. Comparer ses cibles legales a celles de 1194 (aucune regle
    d'empreinte) separe « le canal `feet` rend 1 pour tout le monde » de « le caster occupe
    VRAIMENT une tuile ».

Le montage (build sur la carte du boss, `--explicit-stats`, DRIVE des positions par
`--place`/`--a-place`) et TOUTES les lectures vivent dans
`scripts/python/probe_888_nova_boss_riptide.py` : le probe MESURE, ce test GARDE, une seule
implementation -- aucune divergence possible entre les deux.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_888_nova_boss_riptide as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, pour la MEME raison mesuree que `test_seeker_missile_frequency_lock_live`:
    # ce fichier importe le PROBE, qui importe `ABILITY_CLASSES` -- la fermeture d'import atteint
    # la quasi-totalite de `scripts/python` (`board.py`, `catalog_inject.py`, tout `engine/ai/`).
    # Declarer etroit produirait un FAUX VERT : le test ne serait pas rejoue quand ce qu'il
    # mesure change. ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc
    # `scripts/python/**/*.py` ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle de toutes les gardes : un changement de build peut les faire changer
    # d'avis sans qu'une ligne du port bouge.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de 1194 et 1192. Le verdict depend du code du "
              "port (arbres DSL + CreateShield/AddEffect/AddBondEffect/"
              "AddStaticStatModifierEffect + le selecteur Trench et le trigger IsTrenchTile + la "
              "lecture de l'AbilityState per-ability + les masques de ciblage), du MONTAGE (le "
              "probe, qui porte le drive des positions et TOUTES les lectures ; il depend lui-meme "
              "de la resolution du visualId d'un porteur npc dans `rl_duel.py`), des entrees "
              "versionnees du runner, et du BUILD charge -- l'oracle etant le jeu lui-meme.",
}

NS_PENDING_ATTACK = P.NS_PENDING_ATTACK     # 1414 EffectType.NovaShield_PendingAttack
NS_PENDING_TARGET = P.NS_PENDING_TARGET     # 1415 EffectType.NovaShield_PendingTarget
NS_EXTRA_BLOCK = P.NS_EXTRA_BLOCK           # 1416 EffectType.NovaShield_ExtraBlockChance
NB_PENDING_ATTACK = P.NB_PENDING_ATTACK     # 1409 EffectType.NovaBoost_PendingAttack
NB_PENDING_TARGET = P.NB_PENDING_TARGET     # 1410 EffectType.NovaBoost_PendingTarget


@pytest.fixture(scope="module")
def shield(live_session):
    """UN SEUL runner pour toutes les gardes 1194 : le cast n'est pas rejouable (il consomme
    l'actif ET termine le tour), donc les gardes relisent la MEME mesure."""
    m, dispose = P.measure_shield(live_session, state_name="test_888_shield")
    try:
        yield m
    finally:
        dispose()


@pytest.fixture(scope="module")
def boost(live_session):
    """Runner DISTINCT pour 1192 : le boss est place en (6,2) (couronne contenant une `Trench`) et
    DEUX ennemis sont poses dessus pour armer le gate dynamique
    `NovaBoostAbility$$GetDynamicInvalidCasterReason` (`Count(Enemies(Caster, marked)) > 1`)."""
    m, dispose = P.measure_boost(live_session, state_name="test_888_boost")
    try:
        yield m
    finally:
        dispose()


# ---------------------------------------------------------------- 1194 NovaShield ---
def test_nova_shield_execution_is_ported(shield):
    """Sans cette garde, la decision CHOISIT le cast et l'execution l'IGNORE : 0 effet, 0 bouclier,
    AUCUNE erreur -- le no-op silencieux."""
    assert shield["routed"] == "handler" and shield["ported"] is True, \
        "1194 non portee (routed=%s ported=%s)" % (shield["routed"], shield["ported"])
    assert not shield["cast_error"], "cast natif bloque: %s" % shield["cast_error"]


def test_nova_shield_marked_zone_matches_native_and_witness_discriminates(shield):
    """La zone marquee (`1415` sur les TUILES) = `Target + AdjacentTiles(Target)` FILTREE des
    trenches. La 2e assertion est ce qui empeche un vert qui ne prouve rien."""
    assert shield["off_marked"] == shield["live_marked"], \
        "zone marquee port=%s natif=%s" % (sorted(shield["off_marked"]),
                                           sorted(shield["live_marked"]))
    assert shield["contre_modele"] != shield["live_marked"], (
        "TEMOIN NON DISCRIMINANT : le contre-modele « sans le filtre IsTrenchTile » rend la MEME "
        "zone que le natif (%s) -- aucune tuile Trench dans la couronne, donc ce bras ne prouve "
        "rien sur le filtre." % sorted(shield["live_marked"]))
    assert shield["contre_modele"] - shield["live_marked"], \
        "le contre-modele devrait etre un SUR-ensemble (il ne filtre rien)"


def test_nova_shield_pending_target_source_is_the_tile_itself(shield):
    """La surcharge **5-args** d'`AddEffect` n'a PAS de selecteur source -> chaque TUILE marquee est
    sa propre source. Invisible du nom de la fonction ; seule la cascade (et les instances du port)
    l'exposent."""
    rows = shield["cascade"].get(NS_PENDING_TARGET) or []
    prows = shield["off_pt_sources"]
    assert rows and prows, "aucune instance de 1415 mesuree (accord degenere)"
    assert len(rows) == len(prows), "1415 : %d instance(s) natif vs %d port" % (len(rows),
                                                                               len(prows))
    assert all(r["on"] == r["source"] for r in rows), \
        "natif : la source de 1415 n'est pas la tuile -- %s" % rows
    assert all(r["on"] == r["source"] for r in prows), \
        "port : la source de 1415 n'est pas la tuile -- %s" % prows


def test_nova_shield_bond_and_durations_match_the_cast_cascade(shield):
    """`1416` porte `TurnsFromRounds(nrOfRounds)` ; `1414` est un BOND a duree DEFAUT sur le
    caster, bonde a LUI-MEME. On compare a la CASCADE (valeur A LA POSE), pas a `decisionView` :
    le cast TERMINE le tour, donc le releve d'apres-cast est deja decremente cote natif et pas
    cote port -- ecart de CANAL, pas de duree."""
    caster = shield["caster"]
    port = (shield["off"].get(caster) or {})
    block = (shield["cascade"].get(NS_EXTRA_BLOCK) or [{}])[0]
    assert int(block.get("remaining") or 0) == int(port.get(NS_EXTRA_BLOCK, -1)), \
        "duree de 1416 : natif(pose)=%s port=%s" % (block.get("remaining"),
                                                    port.get(NS_EXTRA_BLOCK))
    bond = (shield["cascade"].get(NS_PENDING_ATTACK) or [{}])[0]
    assert bond.get("on") == caster and bond.get("bonded") == caster, \
        "1414 natif : on=%s bonded=%s (attendu le caster u%s)" % (bond.get("on"),
                                                                  bond.get("bonded"), caster)
    off_bond = shield["off_bonds"].get(NS_PENDING_ATTACK) or {}
    assert off_bond.get("on") == caster and off_bond.get("bonded") == caster, \
        "1414 port : %s" % off_bond


def test_nova_shield_amount_uses_the_per_ability_state(shield):
    """`Shields_InitialAmount` de la cascade == le `shieldHp` du port. C'est l'etage qui separe
    l'`AbilityState` PER-ABILITY (level 55 x multiplier 200) du canal global (0 / 100) : sur un
    porteur npc, le second rend l'entree de niveau 0 -- un facteur 137."""
    nat = [int(s["amount"]) for s in shield["cascade_shields"] if s.get("amount") is not None]
    prt = [int(s["amount"]) for s in shield["off_shields"]]
    assert nat and prt, "aucun bouclier mesure (accord degenere)"
    assert nat[0] == prt[0], "montant du bouclier natif=%d port=%d" % (nat[0], prt[0])


def test_nova_shield_cast_deals_no_damage(shield):
    """La REFUTATION de l'audit `DAMAGE(Particle)` : le cast ne touche AUCUN PV, des deux cotes."""
    ob, oa = shield["off_hp"]
    lb, la = shield["live_hp"]
    assert ob == oa, "le PORT a change des PV : %s -> %s" % (ob, oa)
    assert lb == la, "le NATIF a change des PV : %s -> %s" % (lb, la)


def test_nova_shield_caster_footprint_agrees_with_the_native_gate(shield):
    """L'empreinte du caster, jugee par un TEMOIN NATIF et non par le canal `feet` seul : `1193
    NovaCharge` porte `CasterHas7Tiles` et refuse tout caster dont `GetFeetCount != 7`. Les deux
    lectures doivent CONCORDER -- sinon l'une des deux ment (canal qui sous-compte, ou regle qui
    ne mord pas)."""
    feet_n = len(shield["feet"])
    charge = shield["charge_from_here"]
    assert (feet_n == 7) == (charge > 0), (
        "INCOHERENCE empreinte : `feet`=%d mais 1193 (`CasterHas7Tiles`) rend %d cible(s) legale(s)"
        % (feet_n, charge))


# ----------------------------------------------------------------- 1192 NovaBoost ---
def test_nova_boost_execution_is_ported(boost):
    assert boost["routed"] == "handler" and boost["ported"] is True, \
        "1192 non portee (routed=%s ported=%s)" % (boost["routed"], boost["ported"])
    assert not boost["cast_error"], "cast natif bloque: %s" % boost["cast_error"]
    assert boost["from_here_count"] >= 1, (
        "MONTAGE KO : le natif refuse le cast -- le gate dynamique "
        "`GetDynamicInvalidCasterReason` (>= 2 ennemis dans la couronne) n'est pas arme")


def test_nova_boost_marked_zone_is_the_ring_without_the_origin(boost):
    """`GetMarkedTilesSelector` = `AdjacentTiles(Caster)` FILTREE -- **sans** `op_Addition` avec
    l'origine (c'est la difference structurelle avec 1194, et le contre-modele la garde)."""
    assert boost["off_marked"] == boost["live_marked"], \
        "zone marquee port=%s natif=%s" % (sorted(boost["off_marked"]),
                                           sorted(boost["live_marked"]))
    assert boost["caster_pos"] not in boost["live_marked"], \
        "la tuile du caster ne doit PAS etre marquee par 1192 (%s)" % sorted(boost["live_marked"])
    assert boost["contre_modele"] != boost["live_marked"], (
        "TEMOIN NON DISCRIMINANT : le contre-modele « sans le filtre IsTrenchTile » rend la MEME "
        "couronne que le natif (%s)." % sorted(boost["live_marked"]))


def test_nova_boost_pending_target_source_is_the_caster(boost):
    """La surcharge **6-args** d'`AddEffect` passe `Caster@+0x48` en source : AUCUNE des instances
    de 1410 n'a la tuile pour source. C'est le miroir exact de la garde 1194 ci-dessus, et les deux
    sens sont necessaires (un port qui confondrait les surcharges en passerait une des deux)."""
    rows = boost["cascade"].get(NB_PENDING_TARGET) or []
    prows = boost["off_pt_sources"]
    assert rows and prows, "aucune instance de 1410 mesuree (accord degenere)"
    assert len(rows) == len(prows), "1410 : %d instance(s) natif vs %d port" % (len(rows),
                                                                               len(prows))
    assert not any(r["on"] == r["source"] for r in rows), \
        "natif : une source de 1410 est la tuile -- %s" % rows
    assert not any(r["on"] == r["source"] for r in prows), \
        "port : une source de 1410 est la tuile -- %s" % prows
    assert all(r["source"] == boost["caster"] for r in rows), \
        "natif : la source de 1410 n'est pas le caster -- %s" % rows


def test_nova_boost_bond_is_on_the_caster(boost):
    """`1409` = BOND sur le CASTER (`source`/`targets` = `Caster@+0x48`), `bondedEntity` =
    `Owner@+0x30` -- qui coincide avec le caster pour une ACTIVE, mais le port CITE les deux slots
    que le natif cite."""
    caster = boost["caster"]
    bond = (boost["cascade"].get(NB_PENDING_ATTACK) or [{}])[0]
    assert bond.get("on") == caster and bond.get("bonded") == caster, \
        "1409 natif : on=%s bonded=%s (attendu u%s)" % (bond.get("on"), bond.get("bonded"), caster)
    off_bond = boost["off_bonds"].get(NB_PENDING_ATTACK) or {}
    assert off_bond.get("on") == caster and off_bond.get("bonded") == caster, \
        "1409 port : %s" % off_bond


def test_nova_boost_cast_deals_no_damage(boost):
    ob, oa = boost["off_hp"]
    lb, la = boost["live_hp"]
    assert ob == oa, "le PORT a change des PV : %s -> %s" % (ob, oa)
    assert lb == la, "le NATIF a change des PV : %s -> %s" % (lb, la)
