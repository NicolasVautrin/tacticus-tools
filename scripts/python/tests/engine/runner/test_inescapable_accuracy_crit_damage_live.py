"""CLIQUET #366-r1 -- `InescapableAccuracy_extraCritDmg` (1116) sur `eldarMauganRa`.

L'effet est pose a l'INIT du passif `InescapableAccuracy` (TriggeredAbilityType 0x45b = 1115) sur
son PORTEUR, avec ses deux jumeaux, par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour` :
`AddEffect(0x45b) + AddEffect(0x45c) + AddEffect(0x45d)`, targets = Owner, `turns = NULL`
(PERMANENTS -- ce qui les eteint est la CONDITION, pas une duree).

TROIS ARTEFACTS GARDES, chacun avec sa vue ROUGE mesuree (fiche
`docs/rl/case-366-r1-inescapable-accuracy-crit-damage.md`) :

  * CANAL  -- `...InescapableAccuracy_ExtraCritDamageEffect$$CreateCritDamageBonus` =
              `ForAddition(get_OwnerIsCaster & IsRangedAttack, ConfigVar(0x42 = extraCritDmg))`.
              Il alimente `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`,
              consomme par `...$$CalculateCriticalDamage` : 1116 ne decide PAS si le coup crite
              (c'est 1115), il decide de COMBIEN.
  * GATE MOUVEMENT -- `CreateActiveCondition` (corps PARTAGE par les trois classes du passif) =
              `op_LogicalNot(HasFlag(Owner, 0 = UnitFlag.Moved))`.
  * GATE ATTAQUE   -- le noeud `IsRangedAttack` du trigger : au CONTACT, l'`ActiveCondition` est
              pourtant VRAIE et le bonus ne doit RIEN ajouter.

Les trois bras tirent une salve d'UN coup (seed BC) : c'est le CONTOURNEMENT du residu MESURE
`#366-r1-crit-multihit` (l'etage CRIT diverge des le 3e coup d'une salve, independamment de toute
ability -- reproduit sur `necroDestroyer` et en melee ; tague `[fable]`, hors de ce cas).

⚠ Ce module NE neutralise PAS `extraCritDmg` dans le seed BC (ce que faisait le montage de 1115
tant que 1116 n'etait pas porte) : le patch vit dans le BC -- donc cote NATIF -- alors que le port
lit `gameconfig` par `magnitude.ability_var`. Le laisser intact est la seule facon d'avoir les deux
modeles sur la MEME entree.

Probe de mesure : `probe_366_r1_inescapable_accuracy_crit_damage.py` (foyer unique du montage --
`stage`/`stage_melee`, `strike` et `replay` sont IMPORTES ici plutot que re-transcrits).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import charge_regime                          # noqa: E402,F401  (fixture)

from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki import (                        # noqa: E402
    InescapableAccuracyExtraCritChanceEffect, InescapableAccuracyExtraCritDamageEffect)
from probe_366_r1_inescapable_accuracy_crit_chance import (       # noqa: E402
    MAUGAN, neutralized_seed_bc, stage, strike)
from probe_366_r1_inescapable_accuracy_crit_damage import (       # noqa: E402
    EFFECT_NAME, EFFECT_TYPE, carried, melee_seed_bc, replay, stage_melee)

_A_UNITS = "necroWarden,necroOverlord"       # aucun des deux ne porte `Overwatch` (cf. le probe)
#: `CritChance` de BASE du porteur = **100**. Ce n'est pas un confort : 1116 ne modifie que le
#: MONTANT d'un crit. Il faut donc que le coup CRITE dans les DEUX bras de mouvement, sans quoi le
#: bras MOVED ne traverserait meme pas `CalculateCriticalDamage` et ne garderait rien.
_CRIT = "100,700"
#: Seeds BC du module : arme(s) a UN coup. Le RANGED patche `Weapons[IsRanged]`, le MELEE patche
#: les DEUX armes (le bras de contact frappe avec `weapons[0]`, 5 coups au kit).
_SEED_BC, _SEED_BC_REPORT = neutralized_seed_bc()
_SEED_BC_MELEE, _SEED_BC_MELEE_REPORT = melee_seed_bc()

#: `extraCritDmg[niveau 50]` du gameconfig, et sa valeur EFFECTIVE au rank normalise du montage
#: (`AbilityVariablesMultiplierPercentage = 180`). L'ecart entre les deux est exactement ce que la
#: mutation `NOSCALE` du probe fait rougir en live.
_BASE_L50 = 554
_SCALED_180 = 997                                   # round(554 * 180 / 100)


def _extra(seed_bc, crit: str = _CRIT):
    """Options de build. `--block-target 0,0` met `BlockChance/BlockDamage` de la cible a zero,
    c'est-a-dire le BLOCAGE DE DEGAT (`GetStat(7/8)` -> `DamageCalculations$$CalculateBlockChances`),
    qui retire un tirage du flux et rend la salve comparable coup a coup.

    ⚠ RECTIFICATION (case-366-r1/1117) : ce n'est **PAS** le canal `BaseEffect$$BlockHitsReduction`
    de `1117 InescapableAccuracy_overrideHits`, contrairement a ce que disaient les redactions de
    1115 et 1116. Les deux « block » n'ont rien en commun : l'un est une stat de DEGAT de la cible,
    l'autre un interrupteur de l'axe COUPS. `1117` n'a jamais ete neutralise par cette option -- il
    etait simplement INERTE dans ces montages, faute de la moindre reduction de coups sur
    `necroWarden`/`necroOverlord` (aucun des deux ne porte Parry, Camouflage, LightCover, Diminutive
    ni BigTarget). Depuis que `1117` est PORTE, il reste inerte pour la meme raison, des deux cotes."""
    return ["--crit", crit, "--block-target", "0,0", "--seed-bc", seed_bc]


def _measure(charge_regime, kind, seed="777", board="MC1_67"):
    """Monte le bras (`NOMOVE` / `MOVED` / `MELEE`), tire, rejoue offline. ECHEC FORT si le regime
    n'est pas atteint -- un `skip` VERT mentirait sur une garde qui n'a rien garde.

    Rend `(h, rec, live)`. Le natif joue UN coup (seed BC) ; le port en produit cinq ou six (il
    derive le nombre de coups du GAMECONFIG par visualId, pas du BC -- residu de SOURCE nomme dans
    la fiche), d'ou la confrontation sur le PREFIXE de longueur `len(live)` : les seules cellules ou
    les deux modeles sont sur la MEME case du flux PRNG."""
    melee = kind == "MELEE"
    h = charge_regime(p_units=MAUGAN, a_units=_A_UNITS, seed=seed, board=board,
                      extra=_extra(_SEED_BC_MELEE if melee else _SEED_BC))
    rec, why = stage_melee(h) if melee else stage(h, kind == "MOVED")
    assert rec is not None, "regime NON ATTEINT (%s) : %s" % (kind, why)
    live, why = strike(h, rec)
    assert live is not None, "salve non mesurable : %s" % why
    assert len(live) == 1, (
        "le natif a joue %d coups, 1 attendu -- le seed BC 1-coup n'a pas pris, la mesure "
        "retomberait dans le regime du residu CRIT pre-existant" % len(live))
    return h, rec, live


@pytest.fixture(scope="module")
def ia_nomove(charge_regime):
    """BRAS NOMOVE -- Maugan Ra n'a pas bouge : l'`ActiveCondition` est VRAIE, le natif frappe a
    `critDmg = GetStat(10) + extraCritDmg` (= 700 + 997 au montage)."""
    return _measure(charge_regime, "NOMOVE")


@pytest.fixture(scope="module")
def ia_moved(charge_regime):
    """BRAS MOVED -- Maugan Ra a fait UN pas (en restant a portee ET hors contact) : `UnitFlag.Moved`
    est pose, l'effet est INACTIF, le natif frappe a `critDmg = GetStat(10)` seul. Le coup crite
    quand meme (`GetStat(9) = 100`), donc le bras mesure le GATE sur le MONTANT."""
    return _measure(charge_regime, "MOVED")


@pytest.fixture(scope="module")
def ia_melee(charge_regime):
    """BRAS MELEE -- Maugan Ra frappe AU CONTACT sans avoir bouge : l'`ActiveCondition` est VRAIE et
    c'est `IsRangedAttack` qui ferme. Le bras isole le noeud d'ATTAQUE, seul."""
    return _measure(charge_regime, "MELEE")


@pytest.fixture(scope="module")
def ia_alt(charge_regime):
    """GENERALISATION -- meme invariant, AUTRE board (`C1_25`, a elevation), AUTRE seed (31337)."""
    return _measure(charge_regime, "NOMOVE", seed="31337", board="C1_25")


def test_registry_binds_dedicated_class():
    """Garde STRUCTURELLE (offline, sans jeu) : 1116 a sa PROPRE classe, distincte de celle de 1115.

    Les fabriques `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffects
    u003Eb__14_141/142/143` allouent depuis TROIS slots `Il2CppClass*` DIFFERENTS puis appellent le
    MEME corps de `$$.ctor` (dedup IL2CPP) : le ctor « fondu » ne fait PAS une classe commune. Les
    trois tables de methodes, relues byte a byte, portent chacune UNE methode propre
    (`CreateBlockHitReductionTrigger` / `CreateCritChanceBonus` / `CreateCritDamageBonus`)."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is InescapableAccuracyExtraCritDamageEffect
    assert InescapableAccuracyExtraCritDamageEffect is not InescapableAccuracyExtraCritChanceEffect
    # `1117` a DEPUIS ete porte (TROISIEME canal, `BaseEffect$$BlockHitsReduction`) et il a sa
    # PROPRE classe : ce qui compte ici reste que les trois soient DISTINCTES.
    from engine.entities.effects.loki import InescapableAccuracyOverrideHitsEffect
    assert EFFECT_CLASSES.get("InescapableAccuracy_overrideHits") \
        is InescapableAccuracyOverrideHitsEffect
    assert InescapableAccuracyOverrideHitsEffect is not InescapableAccuracyExtraCritDamageEffect


def test_gates_are_tristate_offline():
    """Les deux gates se taisent tant que leur contexte ne PROUVE pas le regime, et la magnitude
    est celle du gameconfig, SCALEE.

    Verrouille aussi l'ABSENCE des deux noeuds de `1222 WarHowl_ExtraDamage_Unstoppable`
    (`IsNormalAttack`, `AmountIsGreaterThanZero`) : les ajouter « par analogie avec le voisin »
    rendrait le port FAUX sur les attaques d'ability."""
    def mk(mult=100):
        return InescapableAccuracyExtraCritDamageEffect(
            name=EFFECT_NAME, effect_type=EFFECT_TYPE, level=1, ability_level=50,
            ability_variables_multiplier=mult)

    e = mk(180)
    assert e.create_effect_crit_damage_bonus_for_attack(None) is None            # ctx absent
    assert e.create_effect_crit_damage_bonus_for_attack({"is_ranged": None}) is None
    assert e.create_effect_crit_damage_bonus_for_attack({"is_ranged": False}) is None  # melee
    # #589-r1-r1 : `get_OwnerIsCaster` a MIGRE du canal vers la classe (le balayage crit est
    # desormais BOARD-WIDE, `board_effect_carriers`). L'identite du porteur fait donc partie du
    # contexte du canal, et un `att_ctx` sans elle ferme le PREMIER noeud -- ce n'est pas un
    # assouplissement du test, c'est le noeud lu a sa nouvelle place native.
    ok = {"is_ranged": True, "has_moved": False, "owner_id": 1, "att_id": 1}
    assert e.create_effect_crit_damage_bonus_for_attack(ok) == _SCALED_180
    assert e.create_effect_crit_damage_bonus_for_attack({**ok, "has_moved": True}) is None, \
        "ActiveCondition NOT HasFlag(Owner, Moved) : une unite qui a bouge ne recoit RIEN"
    # AUCUN des deux noeuds de 1222 n'existe ici.
    assert e.create_effect_crit_damage_bonus_for_attack({**ok, "is_normal_attack": False}) \
        == _SCALED_180, "pas de noeud IsNormalAttack -> le bonus vaut aussi pour une ABILITY"
    assert e.create_effect_crit_damage_bonus_for_attack({**ok, "caster_crit_chance": 0}) \
        == _SCALED_180, "pas de noeud AmountIsGreaterThanZero -> aucun gate sur GetStat(9)"
    # `is_active` = le MEME predicat, sur l'autre voie (tout consommateur d'`active_effects`).
    assert e.is_active({"has_moved": False}) is True
    assert e.is_active({"has_moved": True}) is False
    assert e.is_active({}) is True, "cle absente = non mesuree -> on ne ferme pas"


def test_rarity_scaling_asymmetry_offline():
    """L'ASYMETRIE de config entre les deux volets, verrouillee : `variablesAffectedByRarityBonus`
    de `InescapableAccuracy` vaut exactement `["extraCritDmg"]`.

    Consequence : 1116 est scale par le multiplicateur du porteur, 1115 ne l'est PAS. C'est le seul
    endroit ou les deux jumeaux divergent, et transposer la phrase « pas de scaling » de 1115 a 1116
    donnerait `554` au lieu de `997` -- ecart que la mutation `NOSCALE` du probe fait rougir LIVE."""
    import gameconfig as GC
    assert (GC.ability("InescapableAccuracy") or {}).get("variablesAffectedByRarityBonus") \
        == ["extraCritDmg"]
    # #589-r1-r1 : l'identite du porteur fait partie du contexte du canal depuis que
    # `get_OwnerIsCaster` a MIGRE vers la classe (balayage crit BOARD-WIDE).
    ranged = {"is_ranged": True, "has_moved": False, "owner_id": 1, "att_id": 1}
    for mult, want in ((100, _BASE_L50), (180, _SCALED_180)):
        dmg = InescapableAccuracyExtraCritDamageEffect(
            name=EFFECT_NAME, effect_type=EFFECT_TYPE, level=1, ability_level=50,
            ability_variables_multiplier=mult)
        assert dmg.create_effect_crit_damage_bonus_for_attack(ranged) == want
        chance = InescapableAccuracyExtraCritChanceEffect(
            name="InescapableAccuracy_extraCritChance", effect_type=1115, level=1, ability_level=50,
            ability_variables_multiplier=mult)
        assert chance.create_effect_crit_chance_bonus_for_attack(ranged) == 15, \
            "extraCritChance N'EST PAS scalee : 15 quel que soit le multiplicateur"


def test_crit_damage_matches_native(ia_nomove):
    """CAS ROUGE AVANT LE FIX -- le crit d'un Maugan Ra IMMOBILE vaut `GetStat(10) + extraCritDmg`
    cote natif ; un port sans le canal frappe a `GetStat(10)` seul."""
    h, rec, live = ia_nomove
    res = h.replay_offline(rec)
    assert carried(rec, res["state"]), \
        "1116 n'est pas materialise offline sur l'attaquant -- le test comparerait deux absences"
    assert res["per_hit"][:len(live)] == live, (
        "CANAL : le port ne compte pas la contribution de 1116 -- live=%s offline=%s"
        % (live, res["per_hit"][:len(live)]))


def test_channel_actually_bites(ia_nomove):
    """Le bras NOMOVE EXERCE bien le canal -- sinon le test precedent passerait pour une raison
    TRIVIALE (aucun bonus nulle part, deux zeros qui s'accordent).

    Mutation ADVERSARIALE : l'inscription est retiree d'`EFFECT_CLASSES`, l'effet capte retombe sur
    `BaseEffect` (qui rend None). Le rejeu DOIT alors differer du rejeu de REFERENCE (et pas du
    live : comparer au live serait vide de sens si les deux divergeaient deja)."""
    h, rec, live = ia_nomove
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert mut[:n] != ref[:n], (
        "l'inscription retiree ne change RIEN au rejeu (ref=%s) -- ce tir n'exerce pas le canal"
        % (ref[:n],))


def test_rarity_scaling_is_load_bearing(ia_nomove):
    """Le SCALING de rarete est charge utile, mesure LIVE -- pas seulement une regle de config.

    Mutation ADVERSARIALE : le multiplicateur force a 100 (donc `554` au lieu de `997`). Le rejeu
    DOIT differer de la reference, sinon rien ne distinguerait les deux lectures."""
    h, rec, live = ia_nomove
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOSCALE")
    assert mut[:n] != ref[:n], (
        "multiplicateur force a 100 : le rejeu ne bouge pas (ref=%s) -- le scaling ne serait pas "
        "exerce par ce coup" % (ref[:n],))


def test_move_closes_the_gate(ia_moved):
    """BRAS MOVED -- apres UN pas, le natif N'AJOUTE PLUS le bonus (`HasFlag(Owner, Moved)`), et le
    port non plus. Le coup CRITE quand meme (`GetStat(9) = 100`) : c'est bien le MONTANT qui change."""
    h, rec, live = ia_moved
    res = h.replay_offline(rec)
    assert carried(rec, res["state"]), \
        "1116 doit rester MATERIALISE (il est PERMANENT) -- c'est la CONDITION qui l'eteint"
    assert res["per_hit"][:len(live)] == live, (
        "GATE MOUVEMENT : live=%s offline=%s" % (live, res["per_hit"][:len(live)]))


def test_move_gate_is_load_bearing(ia_moved):
    """Le gate de mouvement est CHARGE UTILE, pas decoratif.

    Mutation ADVERSARIALE : les DEUX mirrors de l'`ActiveCondition` de 1116 sont desarmes. Le port
    se remet a frapper a `700 + 997` la ou le natif frappe a `700` -> le rejeu DOIT differer."""
    h, rec, live = ia_moved
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOGATE")
    assert mut[:n] != ref[:n], (
        "gate desarme : le rejeu ne bouge pas (ref=%s) -- ce bras ne prouve pas que la condition "
        "mord" % (ref[:n],))


def test_melee_closes_the_gate(ia_melee):
    """BRAS MELEE -- au CONTACT, `IsRangedAttack` ferme le canal alors que l'`ActiveCondition` est
    VRAIE. C'est le seul bras qui mesure le noeud d'ATTAQUE isole du noeud de MOUVEMENT."""
    h, rec, live = ia_melee
    res = h.replay_offline(rec)
    assert carried(rec, res["state"]), "1116 doit etre MATERIALISE meme quand son gate ferme"
    assert res["per_hit"][:len(live)] == live, (
        "GATE ATTAQUE : live=%s offline=%s" % (live, res["per_hit"][:len(live)]))


def test_melee_gate_is_load_bearing(ia_melee):
    """Mutation ADVERSARIALE : `IsRangedAttack` desarme. Le port appliquerait alors le bonus a une
    frappe de contact -> le rejeu DOIT differer de la reference."""
    h, rec, live = ia_melee
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NORANGEGATE")
    assert mut[:n] != ref[:n], (
        "`IsRangedAttack` desarme : le rejeu ne bouge pas (ref=%s) -- ce bras ne prouve pas que le "
        "gate d'attaque mord" % (ref[:n],))


def test_other_board(ia_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`, a ELEVATION -- le crit traverse donc
    aussi l'etage %-list), autre seed (31337)."""
    h, rec, live = ia_alt
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    assert carried(rec, h.replay_offline(rec)["state"])
    assert ref[:n] == live, "C1_25/31337 : live=%s offline=%s" % (live, ref[:n])
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert mut[:n] != ref[:n], \
        "C1_25/31337 : la mutation ne change rien -- ce bras n'exerce pas le canal"
