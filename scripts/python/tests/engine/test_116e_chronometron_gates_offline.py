"""#116-e -- les GATES de `Chronometron_ExtraDamage` (1550), et le canal qui les alimente.

Le residu #116-e decrivait cet effet comme POSE mais INERTE : trois entrees manquaient dans
l'`attacker_ctx` du hook DEFENSEUR (equipe de l'attaquant vs equipe de la SOURCE, trait
`Mechanical` de l'attaquant, compteur `TimesEffectApplied`). Re-mesure : il est VIVANT depuis
`8fe05a62`. Ce fichier n'ouvre donc rien -- il FERME, en gardant ce qui n'etait garde par rien.

CE QUI MANQUAIT AU PARC. `test_462_r4b_r1_r1_defender_additive_carriers_offline` couvre cet effet,
mais seulement gate OUVERT (magnitude non nulle et INTEGRALE). Un test qui ne verifie que
l'ouverture ne peut pas voir un gate qui s'ouvre TOUJOURS : supprimer le `AreFriends` le laisserait
VERT, et l'effet majorerait le degat inflige par les ENNEMIS du Chronomancer. Les quatre regimes de
FERMETURE et la discrimination `IsMechanical` sont donc ici.

L'ARBRE NATIF, verbatim
(`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`) :

    trigger = get_OwnerIsTarget & IsUnit(caster@0x160)
                                & AreFriends(caster@0x160, EffectSource(Effect@0x150))
    montant = Multiply( If( IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2),
                                                        ConfigVar(8 = extraDmg) ),
                        TimesEffectApplied(Effect@0x150) )
    kind    = ForAddition   (additif PLAT ; slot `+0x10` de `EffectBonus`)

⚠ Le membre DROIT d'`AreFriends` est `EffectSource(Effect@0x150)` = le POSEUR (le Chronomancer),
PAS l'attaquant : c'est la raison d'etre de la cle `team_by_id`, et le seul point ou une lecture
distraite ferait comparer l'attaquant a lui-meme -- un gate qui serait alors TOUJOURS vrai.

Les MAGNITUDES ne sont pas ecrites en dur : elles sont re-derivees du gameconfig par le test, et
seuls les RAPPORTS et les FERMETURES sont assertes. Un rebalancement du jeu ne doit pas rougir ici
(il ferait rougir un test d'egalite a un litteral), mais un gate perdu, si.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": True,
    "raison": "`chemins` VIDE parce que `probe_486r15 --proposer` mesure que la fermeture d'imports "
              "de ce fichier (450 modules) tient ENTIEREMENT dans la cascade derivee du foyer, "
              "qu'on ne redeclare pas (#531) -- il ne reste donc rien a borner, et un perimetre "
              "vide avec `toujours: False` ne serait JAMAIS rejoue. D'ou `toujours: True` : le "
              "fichier est offline et court (7 tests, ~2 s, aucun runner), le cout de le rejouer a "
              "chaque passe est negligeable devant ce qu'il garde -- les quatre FERMETURES de gate "
              "de l'effet 1550, qu'aucun autre test ne voit (le garde existant ne mesure que le "
              "gate OUVERT, donc il reste vert si `AreFriends` disparait). `build: False` : aucune "
              "valeur n'est figee depuis le binaire, les magnitudes sont re-derivees du gameconfig "
              "a chaque passe et seule la STRUCTURE des gates est assertee.",
}

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EffectFactory

_SRC = 900          # le Chronomancer, POSEUR de l'effet (`EffectSource(Effect@0x150)`)
_ATT = 901          # l'attaquant (`caster@0x160`)
_NAME = "Chronometron_ExtraDamage"


def _effect(times_applied: int = 1, level: int = 50):
    e = EffectFactory.create({"name": _NAME,
                              "effectType": int(EffectType.Chronometron_ExtraDamage),
                              "remaining": 1, "active": True})
    e.source = _SRC
    e.active_ability_level = level
    e.ability_level = level
    e.ability_variables_multiplier = 100
    e.times_applied = times_applied
    return e


def _attacker(**over):
    """Contexte NOMINAL : attaquant unite, ALLIE du poseur, NON mecanique. Chaque test n'en
    modifie qu'UNE cle -- c'est ce qui attribue une fermeture a un gate et a un seul."""
    ctx = {"id": _ATT, "is_unit": True, "team": 1,
           "team_by_id": {_SRC: 1, _ATT: 1},
           "traits": ("Necron",)}
    ctx.update(over)
    return ctx


def _bonus(effect, attacker_ctx):
    return effect.create_effect_damage_malus_for_defense(
        is_melee=True, damage_profile="Physical", attacker_ctx=attacker_ctx)


def test_nominal_is_a_flat_positive_addition_on_the_defender():
    """ANTI-VACUITE. Si ce cas rendait None, les six tests de fermeture ci-dessous passeraient tous
    pour de MAUVAISES raisons (un effet mort ferme tous ses gates). Il ouvre le fichier."""
    b = _bonus(_effect(), _attacker())
    assert b is not None, (
        "gate NOMINAL ferme : l'effet est redevenu INERTE -- c'est #116-e qui se rouvre, et tous "
        "les gardes de fermeture de ce fichier deviennent vacues")
    assert b.kind == "Addition", "kind = %r -- le natif ecrit `ForAddition` (slot +0x10)" % b.kind
    assert b.owner_is_caster is False, "l'effet vit sur la CIBLE (`get_OwnerIsTarget`)"
    assert b.value > 0


def test_mechanical_attacker_reads_the_OTHER_config_var():
    """`If(IsMechanical(caster), ConfigVar(9 = extraDmg_2), ConfigVar(8 = extraDmg))`.

    On asserte que les deux branches DIFFERENT, pas leurs valeurs : c'est la seule facon de garder
    la discrimination sans rougir a chaque rebalancement. Si les deux `ConfigVar` devenaient egaux
    au gameconfig, le test le DIT au lieu de passer en silence -- une branche indiscernable ne
    prouve rien."""
    import gameconfig as GC
    cfg = ((GC.ability("Chronometron") or {}).get("variables") or {})
    if not (cfg.get("extraDmg") and cfg.get("extraDmg_2")):
        pytest.fail("`Chronometron.variables` ne porte plus extraDmg/extraDmg_2 : le montage de ce "
                    "test ne discrimine plus rien (gameconfig = %r)" % sorted(cfg))

    plain = _bonus(_effect(), _attacker())
    mecha = _bonus(_effect(), _attacker(traits=("Necron", "Mechanical")))
    assert mecha is not None and plain is not None
    assert mecha.value != plain.value, (
        "attaquant MECANIQUE et non-mecanique rendent la MEME magnitude (%s) : soit le `If("
        "IsMechanical(...))` a saute, soit extraDmg == extraDmg_2 au gameconfig -- dans les deux "
        "cas ce garde ne discrimine plus" % plain.value)


@pytest.mark.parametrize("trait", ["Mechanical", "LivingMetal", "Vehicle"])
def test_is_mechanical_is_a_disjunction_of_THREE_traits(trait):
    """LE BUG QUE CE FICHIER A TROUVE. `IdunBattle.Entities.UnitExtensions$$IsMechanical` =

        HasTrait(0x5 Mechanical) || HasTrait(0x3e8 LivingMetal) || HasTrait(0x405 Vehicle)

    Le site testait `"Mechanical" in traits`. Le raccourci ne leve pas : il lit l'AUTRE branche du
    `If` et rend `extraDmg` au lieu d'`extraDmg_2` -- une magnitude fausse, en silence.

    C'est le camp NECRON qui le paie : `Chronometron` est une ability necron, ses allies portent
    `LivingMetal` et non `Mechanical`. Le regime le plus frequent de cet effet etait donc
    precisement celui que le port ratait, et aucun test ne le voyait (le seul garde existant
    n'exerce que le cas non-mecanique).

    Les trois traits sont testes SEPAREMENT : un helper qui n'en couvrirait que deux passerait un
    test qui les poserait ensemble."""
    plain = _bonus(_effect(), _attacker(traits=("Necron",)))
    mecha = _bonus(_effect(), _attacker(traits=("Necron", trait)))
    assert plain is not None and mecha is not None
    assert mecha.value != plain.value, (
        "trait `%s` : l'attaquant n'est pas reconnu MECANIQUE (meme magnitude %s que sans le "
        "trait) -- `IsMechanical` a ete relu comme un test de trait UNIQUE" % (trait, plain.value))


def test_enemy_attacker_closes_the_AreFriends_gate():
    """LE GATE QUE RIEN NE GARDAIT. `AreFriends(caster@0x160, EffectSource(Effect@0x150))` : le
    membre DROIT est le POSEUR, pas l'attaquant. Un attaquant de l'equipe ADVERSE du Chronomancer
    ne doit RIEN recevoir -- sinon l'effet majore le degat de ceux contre qui il a ete lance."""
    b = _bonus(_effect(), _attacker(team=2, team_by_id={_SRC: 1, _ATT: 2}))
    assert b is None, (
        "un attaquant ENNEMI du poseur recoit quand meme %r : le gate `AreFriends` compare "
        "probablement l'attaquant a LUI-MEME (membre droit = `EffectSource`, pas `caster`)" % (b,))


def test_unresolvable_source_team_stays_silent_instead_of_guessing():
    """TRI-ETAT. `team_by_id` vide = equipe du POSEUR non resolvable. Le gate se TAIT (`present !=
    applique`), il ne suppose pas l'amitie. C'est le regime d'un seam qui n'alimente pas la cle --
    exactement l'etat que #116-e decrivait, et qu'on veut voir rendre None plutot qu'un nombre."""
    assert _bonus(_effect(), _attacker(team_by_id={})) is None


def test_non_unit_attacker_closes_the_IsUnit_gate():
    """`IsUnit(caster@0x160)` : une entite-tuile / entite-effet n'est pas un caster valide."""
    assert _bonus(_effect(), _attacker(is_unit=False)) is None


def test_magnitude_is_linear_in_times_effect_applied():
    """`Multiply(<configvar>, TimesEffectApplied(Effect@0x150))` -- compteur PAR INSTANCE
    (`EffectComponent.TimesApplied @+0x6c`), incremente par la re-pose au lieu de creer une seconde
    instance (`runner/operations/effects.py`). La LINEARITE est la propriete testable sans figer
    aucune magnitude."""
    un = _bonus(_effect(times_applied=1), _attacker())
    trois = _bonus(_effect(times_applied=3), _attacker())
    assert un is not None and trois is not None
    assert trois.value == un.value * 3, (
        "TimesEffectApplied = 3 rend %s pour un unitaire de %s -- le `Multiply` a saute ou le "
        "compteur n'est plus lu" % (trois.value, un.value))


def test_zero_times_applied_produces_nothing():
    """Borne basse : un compteur a 0 rend un montant nul, donc AUCUN bonus -- et non un
    `Addition(0)` qui traverserait l'accumulateur pour rien."""
    assert _bonus(_effect(times_applied=0), _attacker()) is None
