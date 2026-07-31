"""#344-r2 -- `SortAttackersByDamagePredictionSelector` : TROIS predictions, pas une.

ARTEFACT NATIF verrouille ici :
`IdunBattle.Entities.Selectors.SortAttackersByDamagePredictionSelector.u003Cu003Ec__DisplayClass8_0$$u003CSelectu003Eb__0`.
Structure LUE au decompile (build `rnca9r7q6c`) :

    hits    = selector@+0x40 . slot 1        # `Calculate`
    dMin    = selector@+0x30 . slot 2        # `CalculateMin`
    dAvg    = selector@+0x30 . slot 4        # `CalculateAverage`
    dMax    = selector@+0x30 . slot 3        # `CalculateMax`
    predMin, predAvg, predMax = query@+0x48 . slot 0x28 (..., dMin | dAvg | dMax, ...)
    key     = 0x7fffffff  si predMax.WillBeKill
              0x7ffffffe  si predMin.MightBeKill
              MinMaxDamage$$Avg(predAvg + 0x60)  sinon        # +0x60 = `TotalDamage`

Le mapping des slots est DERIVE du binaire, pas herite d'un rapport :
`IdunBattle.Entities.Formulas.PercentageOf$$Calculate` appelle le slot 1 sur ses deux enfants,
`$$CalculateMin` le slot 2, `$$CalculateMax` le slot 3 -- le slot 4 restant est `CalculateAverage`
(le seul membre d'`IAmountFormula` dont `IdunBattle.DSL.AAmountFormula` porte un corps).

TROIS angles de garde :

* `test_prediction_is_built_three_times_per_attacker` -- le COMPTE (2 attaquants -> 6 evaluations).
* `test_..._is_read_on_the_..._prediction` (x3) -- le CABLAGE, par l'ORDRE rendu : chaque attaquant
  recoit un triplet different, et l'ordre final revele laquelle des cles est la plus grande. Aucune
  introspection : c'est la sortie publique du collapse qui tranche.
* `test_shielded_target_flips_the_attacker_order` -- l'EFFET OBSERVABLE, sans aucune substitution.
  Le champ moyenne par le natif est `TotalDamage@0x60` (= bloque-par-bouclier NON cape + degat sante
  pre-scenario), pas `DefaultScenario.Damage.HealthDamage`. Les deux ne se separent que si la cible
  porte un bouclier : quand il absorbe TOUT, la sante tombe a zero pour tout le monde (donc l'ancien
  port egalisait les cles et departageait par id croissant) alors que `TotalDamage` reste le degat
  brut (donc le natif classe par degat). L'ordre des attaquants s'inverse.

Le noeud de degat de l'unique appelant (`ExemplarOfHateAbility$$GetAttacker`, xrefs LUES : il n'y en
a qu'un) est une `IdunBattle.Entities.Formulas.MinAmount`, donc une `IdunBattle.DSL.ASimpleAmountFormula`,
dont `CalculateMin`/`CalculateMax` retombent sur `Calculate` -- les trois montants COINCIDENT
toujours pour ce porteur. AUCUN montage ne peut donc les separer par la VALEUR du montant : c'est
pourquoi les gardes de cablage passent par l'ORDRE des appels, seul discriminant disponible.

OFFLINE pur (aucune session Frida). ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

from engine.entities import UnitContext
from engine.entities.effects_state import EffectsState
from engine.entities.stats import StatType, UnitStats
from engine.runner.abilities.darkangels import (_exemplar_of_hate_attackers,
                                                sort_attackers_by_damage_prediction_key)
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      ShieldComponent, ShieldInstance, StatsComponent,
                                      UnitComponent)
from engine.runner.state import State
from engine.services.damage_prediction import (DamagePredictionResult, MinMaxDamage,
                                               get_attack_prediction)
from engine.services.min_max_damage import min_max_avg

# Unites DarkAngels reelles (`gameconfig`.FactionId == 'DarkAngels') : le collapse filtre par
# `UnitsFromFaction(..., 10 = DarkAngels)`, un visual_id invente serait ecarte en silence.
CASTER_VID = "darkaAsmodai"        # le porteur de 1140 ExemplarOfHate
ATTACKER_VID = "darkaTerminator"   # arme de melee (Range absent -> portee 1)

TARGET_HP = 100000                 # assez haut pour qu'aucune borne ne declenche kill/might-kill
FRAGILE_HP = 50                    # sous la borne MIN des deux attaquants -> sure-kill sans bouclier
DMG_PCT = 100                      # `dmgPct` : override = 100 % de l'Attack de l'attaquant
NO_CAP = 0                         # `maxDmg` : 0 = pas de plafond (branche `if cap` fausse)
ABSORBING_SHIELD = 10 ** 6         # bouclier qui absorbe TOUT le degat des deux attaquants


def build_exemplar_attacker_scene(*, weak_attack: int, strong_attack: int, target_shield: int,
                                  target_hp: int = TARGET_HP):
    """FIXTURE du collapse `ExemplarOfHateAbility$$GetAttacker`.

    Monte l'etat MINIMAL que `_exemplar_of_hate_attackers` consomme :

      * un caster DarkAngels (`darkaAsmodai`) place HORS de portee de la cible -- il passe les
        filtres `Friends` / `UnitsFromFaction` mais est ecarte par `UnitsWhoCanAttack`, ce qui laisse
        exactement DEUX candidats et rend l'ordre lisible ;
      * l'attaquant FAIBLE avec l'id le PLUS PETIT et le FORT avec l'id le plus grand -- c'est ce qui
        rend le renversement visible : a cles EGALES le tie-break `OrderByDescending` stable met le
        petit id devant, a cles DISTINCTES c'est la cle qui tranche ;
      * une cible ennemie a `target_shield` de bouclier
        (`IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield`).

    Les deux attaquants sont adjacents a la cible (meme colonne, ligne +-1) : ils sont a portee de
    leur arme de melee. Rend `(state, caster_id, target_id, weak_id, strong_id)`."""
    state = State()
    state.effects = EffectsState.seed({})

    def _unit(vid: str, col: int, row: int, team: int, attack: int, shield: int = 0,
              hp: int = TARGET_HP):
        e = state.add_entity()
        e.add_component(UnitComponent(visual_id=vid, alive=True))
        e.add_component(OwnerComponent(team=team, player=(3 if team == 1 else 4)))
        e.add_component(PositionComponent(col=col, row=row))
        e.add_component(HealthComponent(hp=int(hp), hp_max=int(hp)))
        stats = UnitStats()
        stats.ensure_seeded(StatType.ATTACK, int(attack))
        for st in (StatType.FIXED_ARMOR, StatType.EXTRA_HITS, StatType.CRIT_CHANCE,
                   StatType.CRIT_DAMAGE, StatType.BLOCK_CHANCE, StatType.BLOCK_DAMAGE):
            stats.ensure_seeded(st, 0)
        e.add_component(StatsComponent(ctx=UnitContext(
            entity_id=e.id, visual_id=vid, active_ability_level=50, passive_ability_level=50,
            ability_variables_multiplier=100, stats=stats)))
        if shield > 0:
            e.add_component(ShieldComponent(
                [ShieldInstance(shield_id=1, amount=int(shield), remaining=None)]))
        return e.id

    caster_id = _unit(CASTER_VID, col=0, row=0, team=1, attack=1)          # hors de portee
    weak_id = _unit(ATTACKER_VID, col=5, row=4, team=1, attack=weak_attack)
    strong_id = _unit(ATTACKER_VID, col=5, row=6, team=1, attack=strong_attack)
    target_id = _unit(ATTACKER_VID, col=5, row=5, team=2, attack=1, shield=target_shield,
                      hp=target_hp)
    assert weak_id < strong_id, "la fixture exige l'attaquant FAIBLE au plus petit id"
    return state, caster_id, target_id, weak_id, strong_id


def _pred(*, raw_min: int = 0, raw_max: int = 0, total: int = 0, hp: int = TARGET_HP):
    """`DamagePredictionResult` FABRIQUE -- seuls les champs que le lambda natif lit sont poses :
    `CurrentHealth@0x00`, `DefaultScenario.Damage.HealthDamage`@0x1c/0x20 (`raw_health_damage`, les
    bornes de `get_WillBeKill`/`get_MightBeKill`) et `TotalDamage@0x60`."""
    return DamagePredictionResult(
        current_health=int(hp),
        raw_health_damage=MinMaxDamage(min=int(raw_min), max=int(raw_max)),
        total_damage=MinMaxDamage(min=int(total), max=int(total)))


INERT = _pred()                                   # ne tue pas, `TotalDamage` nul
SURE_KILL = _pred(raw_min=TARGET_HP, raw_max=TARGET_HP)   # `get_WillBeKill` VRAI
MAYBE_KILL = _pred(raw_min=0, raw_max=TARGET_HP)          # `get_MightBeKill` VRAI, WillBeKill FAUX
HUGE = _pred(total=10 ** 6)                       # inerte cote kill, `TotalDamage` enorme
SMALL = _pred(total=42)
BIG = _pred(total=100)


def _install_triplets(monkeypatch, *triplets):
    """Substitue le service de prediction par une sequence FIXE : un triplet `(min, avg, max)` par
    attaquant, consomme dans l'ordre d'appel -- qui est celui du natif (le lambda evalue le slot 2,
    puis le slot 4, puis le slot 3, et batit les predictions dans cet ordre). La boucle du port
    itere les entites par id CROISSANT, donc triplet[0] = l'attaquant FAIBLE.

    Rend la liste des `initial_damage` recus (pour compter les evaluations)."""
    seq = [p for t in triplets for p in t]
    seen: list[int] = []

    def _stub(**kwargs):
        seen.append(int(kwargs["initial_damage"]))
        return seq[len(seen) - 1]

    monkeypatch.setattr("engine.services.damage_prediction.get_attack_prediction", _stub)
    return seen


def _two_attackers():
    return build_exemplar_attacker_scene(weak_attack=100, strong_attack=100, target_shield=0)


# --------------------------------------------------------------------------------------------- #
# 1. COMPTE : trois predictions PAR attaquant.
# --------------------------------------------------------------------------------------------- #

def test_prediction_is_built_three_times_per_attacker():
    """Le lambda natif appelle le service de prediction TROIS fois par attaquant (une par borne du
    noeud de degat). Un port qui n'en batit qu'une n'en fait que 2 pour 2 attaquants."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        state, caster, target, _w, _s = _two_attackers()
        seen = _install_triplets(monkeypatch, (INERT, SMALL, INERT), (INERT, SMALL, INERT))
        _exemplar_of_hate_attackers(state, caster, target, NO_CAP, DMG_PCT)
    finally:
        monkeypatch.undo()
    assert len(seen) == 6, (
        "2 attaquants x 3 bornes = 6 evaluations attendues ; observe %d" % len(seen))
    # Les trois montants d'un meme attaquant sont EGAUX (noeud `ASimpleAmountFormula`) : c'est la
    # propriete DEMONTREE au decompile, et la raison pour laquelle seul l'ordre discrimine.
    assert seen[0] == seen[1] == seen[2] and seen[3] == seen[4] == seen[5]


# --------------------------------------------------------------------------------------------- #
# 2. CABLAGE. D'abord la CLE elle-meme (`<Select>b__0`), ou l'appariement borne <-> test est
#    verifiable a la valeur pres -- c'est la garde qui rougit sous N'IMPORTE QUELLE permutation.
# --------------------------------------------------------------------------------------------- #

def test_key_pairs_each_bound_with_its_own_test():
    """L'appariement natif est ASYMETRIQUE : sure-kill sur la borne HAUTE, kill possible sur la
    borne BASSE, moyenne sur la borne MOYENNE. Les trois assertions ci-dessous sont mutuellement
    exclusives : permuter deux arguments quelconques en casse au moins une."""
    # Seul le MAX tue a coup sur -> 0x7fffffff. Si `will_be_kill` etait lu sur le MIN ou l'AVG
    # (tous deux inertes), la cle retomberait sur `might_be_kill` ou sur la moyenne.
    assert sort_attackers_by_damage_prediction_key(INERT, SMALL, SURE_KILL) == 0x7fffffff
    # Seul le MIN peut tuer -> 0x7ffffffe. Si `might_be_kill` etait lu sur le MAX (inerte), on
    # tomberait sur la moyenne (42).
    assert sort_attackers_by_damage_prediction_key(MAYBE_KILL, SMALL, INERT) == 0x7ffffffe
    # Aucun kill -> la moyenne, prise sur le `TotalDamage` de l'AVG (42) et non sur celui du MIN ou
    # du MAX (10^6 tous les deux).
    assert sort_attackers_by_damage_prediction_key(HUGE, SMALL, HUGE) == 42
    # Un sure-kill sur le MAX PRIME sur un might-kill du MIN (ordre des deux `if` natifs).
    assert sort_attackers_by_damage_prediction_key(MAYBE_KILL, SMALL, SURE_KILL) == 0x7fffffff
    # ... et un might-kill du MAX ne compte PAS : seul le MIN alimente `get_MightBeKill`.
    assert sort_attackers_by_damage_prediction_key(INERT, SMALL, MAYBE_KILL) == 42


# --------------------------------------------------------------------------------------------- #
#    Puis le CABLAGE bout-en-bout : le collapse passe bien les trois predictions dans cet ordre.
# --------------------------------------------------------------------------------------------- #

@pytest.mark.parametrize("weak_triplet,strong_triplet,expected,why", [
    # `get_WillBeKill` sur la prediction du slot 3 (MAX) : seul le 3e element du triplet du FAIBLE
    # porte le sure-kill. Un port qui lirait le kill sur la 1re prediction (ou sur l'unique
    # prediction d'avant #344-r2) laisserait le FAIBLE a une cle de 0 et le FORT passerait devant.
    ((INERT, INERT, SURE_KILL), (INERT, HUGE, INERT), "weak-first",
     "`get_WillBeKill` doit etre lu sur la prediction du MAX (slot 3)"),
    # `get_MightBeKill` sur la prediction du slot 2 (MIN) : seul le 1er element du triplet du FAIBLE
    # porte le might-kill, et 0x7ffffffe bat le `TotalDamage` geant du FORT.
    ((MAYBE_KILL, INERT, INERT), (INERT, HUGE, INERT), "weak-first",
     "`get_MightBeKill` doit etre lu sur la prediction du MIN (slot 2)"),
    # La moyenne porte sur `TotalDamage` de la prediction du slot 4 (AVERAGE). Le FAIBLE a un
    # `TotalDamage` ENORME sur ses predictions MIN et MAX mais 42 sur l'AVERAGE ; le FORT a 100 sur
    # l'AVERAGE. Moyenner la mauvaise prediction (ou `raw_health_damage`, nul partout) renverse.
    ((HUGE, SMALL, HUGE), (INERT, BIG, INERT), "strong-first",
     "la moyenne doit porter sur `TotalDamage@0x60` de la prediction de l'AVERAGE (slot 4)"),
])
def test_each_test_is_read_on_its_own_prediction(weak_triplet, strong_triplet, expected, why):
    monkeypatch = pytest.MonkeyPatch()
    try:
        state, caster, target, weak, strong = _two_attackers()
        _install_triplets(monkeypatch, weak_triplet, strong_triplet)
        ranked = _exemplar_of_hate_attackers(state, caster, target, NO_CAP, DMG_PCT)
    finally:
        monkeypatch.undo()
    want = [weak, strong] if expected == "weak-first" else [strong, weak]
    assert ranked == want, why + " -- ordre observe %r, attendu %r" % (ranked, want)


# --------------------------------------------------------------------------------------------- #
# 3. EFFET OBSERVABLE : le bouclier separe `TotalDamage` de la sante, et renverse l'ordre.
# --------------------------------------------------------------------------------------------- #

def _bounds(attack: int, shield: int, hp: int) -> tuple:
    """`(raw_health_damage, total_damage)` d'un attaquant d'`Attack` donnee -- la MESURE qui separe
    les deux champs, re-derivee du service et non recopiee."""
    p = get_attack_prediction(target_current_health=hp, initial_damage=attack, hits=1,
                              profile_type=0, armor=0, pierce_pct=100, spread_pct=20,
                              target_shield=shield)
    return ((p.raw_health_damage.min, p.raw_health_damage.max),
            (p.total_damage.min, p.total_damage.max))


def test_shielded_fragile_target_flips_the_attacker_order():
    """LE montage discriminant, et il est ETROIT -- il faut un bouclier ET une cible fragile.

    Mesure (`_bounds`, Attack 100 / 500, spread 20 %) :

        shield 0        : raw (80,120) / (400,600)   total (80,120) / (400,600)   -> IDENTIQUES
        shield 10^6     : raw (0,0)    / (0,0)       total (80,120) / (400,600)

    Le port d'avant #344-r2 ne passait PAS le bouclier au service ET moyennait `raw_health_damage` :
    deux ecarts qui se COMPENSENT exactement sur la branche moyenne (`TotalDamage` = bloque + sante,
    donc `blk + (base - blk)` = la base, c.-a-d. ce que le port calculait en ignorant le bouclier).
    C'est sur la branche KILL qu'ils cessent de se compenser : avec une cible a `FRAGILE_HP` PV
    derriere un bouclier absorbant, l'ancien port voyait DEUX sure-kills (`raw.min` >= PV pour les
    deux attaquants), donc deux cles egales a 0x7fffffff departagees par l'id CROISSANT ; le natif,
    lui, ne peut pas tuer a travers le bouclier -> aucune borne de kill, et c'est
    `Avg(TotalDamage)` qui classe, donc le plus FORT devant."""
    (raw_w, tot_w) = _bounds(100, ABSORBING_SHIELD, FRAGILE_HP)
    (raw_s, tot_s) = _bounds(500, ABSORBING_SHIELD, FRAGILE_HP)
    assert raw_w == raw_s == (0, 0), "le bouclier de la fixture doit absorber TOUT le degat"
    assert tot_w[0] >= FRAGILE_HP and tot_s[0] >= FRAGILE_HP, (
        "les deux attaquants doivent etre sure-kill SANS le bouclier -- sinon l'ancien port ne "
        "produit pas l'egalite de cles que ce test exploite")
    assert min_max_avg(*tot_s) > min_max_avg(*tot_w), "la cle native doit croitre avec l'Attack"

    state, caster, target, weak, strong = build_exemplar_attacker_scene(
        weak_attack=100, strong_attack=500, target_shield=ABSORBING_SHIELD, target_hp=FRAGILE_HP)
    ranked = _exemplar_of_hate_attackers(state, caster, target, NO_CAP, DMG_PCT)
    assert ranked == [strong, weak], (
        "derriere un bouclier absorbant, aucun attaquant n'est sure-kill : la cle native "
        "`Avg(TotalDamage)` doit departager par le degat et mettre le FORT devant. Observe : %r"
        % (ranked,))


def test_unshielded_target_is_unchanged():
    """NON-REGRESSION : sans bouclier, `TotalDamage` et `raw_health_damage` COINCIDENT (le bloque
    vaut zero) -- le changement de source ne doit rien bouger sur le regime historique, ni sur une
    cible robuste ni sur une cible fragile (ou les DEUX attaquants restent sure-kill)."""
    raw, tot = _bounds(250, 0, TARGET_HP)
    assert raw == tot, "sans bouclier les deux champs doivent coincider"

    state, caster, target, weak, strong = build_exemplar_attacker_scene(
        weak_attack=100, strong_attack=500, target_shield=0)
    assert _exemplar_of_hate_attackers(state, caster, target, NO_CAP, DMG_PCT) == [strong, weak]

    # Cible fragile SANS bouclier : les deux sont sure-kill -> cles egales -> tie-break id croissant.
    state2, caster2, target2, weak2, strong2 = build_exemplar_attacker_scene(
        weak_attack=100, strong_attack=500, target_shield=0, target_hp=FRAGILE_HP)
    assert _exemplar_of_hate_attackers(state2, caster2, target2, NO_CAP, DMG_PCT) == [weak2, strong2]


# --------------------------------------------------------------------------------------------- #
# 4. Les deux mirrors nommes de `DamagePredictionResult`.
# --------------------------------------------------------------------------------------------- #

def test_will_be_kill_reads_the_block_scenario_and_might_be_kill_does_not():
    """`get_WillBeKill` lit `BlockScenarios[0]+0x0c` quand la liste est non vide (= `block_raw_min`),
    `get_MightBeKill` ne lit QUE `DefaultScenario.Damage.HealthDamage.Max` -- l'asymetrie est
    native."""
    p = _pred(raw_min=100, raw_max=100, hp=100)
    assert p.will_be_kill() and p.might_be_kill()

    p.block_raw_min = 99                       # le block du defenseur retire 1 -> plus de sure-kill
    assert not p.will_be_kill(), "`get_WillBeKill` doit PREFERER le scenario de block a `raw.min`"
    assert p.might_be_kill(), "`get_MightBeKill` ignore la liste `BlockScenarios` (aucun gate natif)"

    dead = _pred(raw_min=10, raw_max=10, hp=0)
    assert not dead.will_be_kill() and not dead.might_be_kill()
