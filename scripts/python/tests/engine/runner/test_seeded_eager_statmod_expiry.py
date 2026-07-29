"""R16 x O3 -- GARDE du CROISEMENT : un stat-mod EAGER seede qui expire PAR SON TIMER.

Deux corrections se rencontrent ici, et le croisement n'etait exerce par aucune des deux :

  * **O3** (`EffectsState.on_turn_end`) a rendu le retrait a echeance REEL et GENERIQUE -- mirror de
    `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` (`if (0 < Duration@+0x64) Duration -= 1`,
    CLAMPE a 0) puis `IdunBattle.Entities.Components.EffectComponent$$ShouldBeRemoved` (`HasTurns &&
    Duration == 0`) -> branche `DeactivateEffect` de
    `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`. Offline la marque est `consumed`,
    honoree par TOUS les lecteurs (`has_effect` comprise) -- pas seulement par `active_effects`.
  * **R16** rend la contribution d'un stat-mod EAGER **SEEDE** attribuee par-source, donc retirable.

Sans R16, le croisement produit un etat FRANCHEMENT INCOHERENT : a l'echeance l'effet est retire pour
tous les lecteurs (`has_effect` = False) **mais son buff reste applique** -- mesure sur `origin/master`
(fb9df01) : `Waaagh_ExtraMovement` seede rem=1 -> apres le tick, effet absent et MOVEMENT toujours a 5
au lieu de 4. Le natif, lui, sort la `ValueModification` dans le MEME passage
(`IdunBattle.Operations.EndTurnOperation$$RefreshEffects` enfile `RefreshEffect`, dont la branche de
retrait appelle le virtuel `RevertInternal` = `AStatModifierEffect$$RevertModification`).

DUREES REELLES du gisement EAGER (tranchees au DECOMPILE + au port, pas supposees) -- c'est ce qui
delimite la portee du croisement :

  | effet                                       | pose                                  | duree      |
  |---------------------------------------------|---------------------------------------|------------|
  | `Waaagh_ExtraMovement` (0x44b=1099)         | `AddStaticStatModifierEffect(..., duree@dsl+0xc0 = Direct(1))` | **1 TOUR** |
  | `CursedPlagueBell_ExtraMove` (0x431=1073)   | `CursedPlagueBellMovementAbility$$CreateBehaviour` = `AddEffect(0x431, ..., turns = Nullable<int>(1))` | **1 TOUR** |
  | `BlackRage_ExtraMove` (0x53e=1342)          | `AddEffect(..., Caster(), 0)`         | PERMANENT  |
  | `AnvilShield_FrozenAttackerAdvantage` (0x4b1=1201) | `AddStaticStatModifierEffect` sans override, et 0x4b1 est ABSENT de `StaticBattleRules.Effect$$DefaultAmountOfRounds` | PERMANENT (retire par son trigger `On(UnitPostAbility=0xe)`) |
  | `ProtectorImperative` (0x4df=1247)          | idem, absent de la table              | PERMANENT (`remaining=0` MESURE live) |

=> **DEUX membres du gisement portent un vrai timer** (`Waaagh_ExtraMovement` depuis l'origine,
`CursedPlagueBell_ExtraMove` depuis #224) -- ce sont les seuls que le retrait a echeance concerne. Les
autres partent par une feuille `RemoveEffect` (couverte par `test_seeded_eager_statmod_revert_live.py`)
ou ne partent pas. Le cycle de vie complet de 1073 (pose au debut du tour, expiration en fin de tour,
re-pose au tour suivant) est confronte au natif par
`tests/engine/runner/test_cursed_plague_bell_extramove_live.py`.

Ces tests passent par le VRAI foyer porte (`EndTurnOperation.execute` : tick de TOUTES les entites
puis `revert_stat_mods_of_removed_effects`), pas par une sequence rejouee a la main -- c'est l'ORDRE de
ces deux etages qui est le sujet. 100 % offline (aucun runner) : le cycle de vie est deterministe ; le
FAIT confronte au natif (« le buff redescend quand l'effet part ») l'est par la garde live jumelle.
"""
from __future__ import annotations

import pytest

from engine.entities import EffectFactory, EffectsState, UnitContext
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatType, CAPTURED_SOURCE
from engine.runner.components import OwnerComponent, StatsComponent, UnitComponent
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.state import State

STAT_IDS = {"attack": 0, "movement": 1, "health": 5, "fixedArmor": 16, "critChance": 9}
BASE = {"attack": 1000, "movement": 4, "health": 8000, "fixedArmor": 400, "critChance": 15}
UID = 55
WAAAGH_EXTRA_MOVEMENT = 1099          # 0x44b
PROTECTOR = 1247                      # 0x4df


def _build(captured, delta, *, visual="orksWarboss", level=50, mult=100):
    """`State` minimal reproduisant la voie SEEDE de `snapshot._load_stats_and_effects` : le stat-mod
    est DEJA cuit dans le `Current` capte (`stats`) et son montant est dans `statDelta`."""
    stats = {k: BASE[k] + int(delta.get(k, 0)) for k in BASE}
    su = {"entityId": UID, "visualId": visual, "stats": stats, "statDelta": dict(delta),
          "unitConfig": {"activeAbilityLevel": level, "abilityVariablesMultiplier": mult}}
    effs = EffectFactory.create_many(captured, mult, None, level)
    ctx = UnitContext.from_snapshot(su, None, STAT_IDS, effs)
    st = State()
    ent = st.add_entity(UID)
    ent.add_component(StatsComponent(ctx=ctx))
    ent.add_component(OwnerComponent(player=3, team=1))
    ent.add_component(UnitComponent(visual_id=visual, alive=True))
    st.effects = EffectsState.seed({UID: captured}, {UID: mult})
    st.current_player_id = 3
    return st, ctx


def _waaagh_state(remaining=1):
    amt = int(ability_var("Waaagh", "extraMovement", is_constant=True) or 0)
    assert amt, "extraMovement non resoluble en gameconfig -> scenario vide"
    cap = [{"name": "Waaagh_ExtraMovement", "effectType": WAAAGH_EXTRA_MOVEMENT, "level": 1,
            "remaining": remaining, "source": UID}]
    st, ctx = _build(cap, {"movement": amt})
    return st, ctx, amt


def test_seeded_eager_statmod_leaves_with_its_effect_at_expiry():
    """LE CRITERE du croisement : a l'echeance, l'effet ET son buff partent **dans le MEME passage**.

    Sans R16, `has_effect` devient False (retrait O3 effectif) alors que `GetStat(MOVEMENT)` garde le
    +1 : effet absent, buff present -- l'incoherence exacte que ce test interdit."""
    st, ctx, amt = _waaagh_state(remaining=1)
    before = int(ctx.stat(StatType.MOVEMENT))
    assert st.effects.has_effect(UID, effect_type=WAAAGH_EXTRA_MOVEMENT)
    assert before == BASE["movement"] + amt, "le seed ne reproduit pas le Current capte"

    EndTurnOperation.execute(st, advance=False)

    still_here = st.effects.has_effect(UID, effect_type=WAAAGH_EXTRA_MOVEMENT)
    after = int(ctx.stat(StatType.MOVEMENT))
    assert not still_here, "l'effet a timer n'a pas ete retire a l'echeance (regression O3)"
    assert after == BASE["movement"], (
        "effet RETIRE mais buff CONSERVE : MOVEMENT=%d au lieu de %d (+%d colle a vie). "
        "L'effet a disparu de has_effect, sa ValueModification non."
        % (after, BASE["movement"], after - BASE["movement"]))


def test_seeded_eager_statmod_reverts_exactly_once_and_on_the_right_turn():
    """UNE fois, au BON tour : le revert tombe au tick ou `remaining` atteint 0 -- pas avant (le buff
    tient tant que l'effet dure), pas deux fois (les ticks suivants sont des no-op)."""
    st, ctx, amt = _waaagh_state(remaining=3)
    base = BASE["movement"]
    seen = []
    for _ in range(6):
        eff = st.effects.by_unit[UID][0]
        EndTurnOperation.execute(st, advance=False)
        seen.append((eff.remaining_turns, int(ctx.stat(StatType.MOVEMENT))))

    # remaining 3 -> 2 -> 1 -> 0 : le buff tient sur les 2 premiers ticks, tombe au 3e, puis plus rien.
    assert [m for _, m in seen] == [base + amt, base + amt, base, base, base, base], \
        "profil de revert inattendu (rem, movement) par tick : %s" % (seen,)
    # une SEULE contribution retiree : la source a disparu du per_source, et rien n'est passe en negatif.
    per_source = dict(ctx.stats.components[int(StatType.MOVEMENT)].modification.per_source)
    assert per_source == {} or all(v >= 0 for v in per_source.values()), \
        "double revert : per_source=%s" % (per_source,)
    assert int(ctx.stat(StatType.MOVEMENT)) == base, \
        "sur-revert : MOVEMENT=%d < base %d" % (int(ctx.stat(StatType.MOVEMENT)), base)


def test_expiry_after_explicit_removal_is_a_noop():
    """DOUBLE CHEMIN (le risque que le croisement introduit) : un effet retire EXPLICITEMENT par une
    feuille `RemoveEffect` puis rattrape par le tick d'echeance ne doit PAS voir sa contribution
    retiree une seconde fois. Garde-fou porte : `stat_mod_reverted` sur l'instance + le fait que
    `IdunBattle.Entities.Components.ValueModification$$ReverseModification` retire UNE cle (donc un
    2e passage est structurellement un no-op)."""
    from engine.dsl.effects import ExecutionContext
    from engine.entities.selectors import Caster
    from engine.runner.abilities.behaviours import RemoveEffect, entities_from_state

    st, ctx, amt = _waaagh_state(remaining=3)
    base = BASE["movement"]
    RemoveEffect(WAAAGH_EXTRA_MOVEMENT, Caster()).execute(
        entities_from_state(st, UID, UID), ExecutionContext(state=st, rng=st.rng))
    after_leaf = int(ctx.stat(StatType.MOVEMENT))
    assert after_leaf == base, "la feuille RemoveEffect n'a pas reverte (%d != %d)" % (after_leaf, base)

    for _ in range(4):
        EndTurnOperation.execute(st, advance=False)
        assert int(ctx.stat(StatType.MOVEMENT)) == base, \
            "le tick d'echeance a RE-reverte apres la feuille : MOVEMENT=%d < base %d" \
            % (int(ctx.stat(StatType.MOVEMENT)), base)


def test_permanent_eager_statmod_is_untouched_by_the_expiry_tick():
    """CONTRE-EPREUVE : les membres PERMANENTS du gisement (`remaining = 0` -> `HasTurns` faux, gate
    d'entree `!Removed && HasTurns` de `RemoveOneTurn`) ne doivent RIEN perdre au tick. Mesure live :
    `ProtectorImperative` arrive avec `rem=0`. Sans cette garde, un revert declenche « au tick » au
    lieu de « au retrait » ferait fondre les buffs permanents en silence."""
    amt = int(ability_var("DoctrinaImperatives", "extraArmor", 50, multiplier_pct=152))
    assert amt, "extraArmor non resoluble -> scenario vide"
    cap = [{"name": "ProtectorImperative", "effectType": PROTECTOR, "level": 1,
            "remaining": 0, "source": UID}]
    st, ctx = _build(cap, {"fixedArmor": amt}, visual="admecMarshall", mult=152)
    assert st.effects.by_unit[UID][0].remaining_turns is None, \
        "remaining=0 doit etre materialise PERMANENT (EffectFactory : rem<=0 -> None)"
    before = int(ctx.stat(StatType.FIXED_ARMOR))
    for _ in range(5):
        EndTurnOperation.execute(st, advance=False)
    assert st.effects.has_effect(UID, effect_type=PROTECTOR), \
        "un effet PERMANENT a ete retire par le tick de duree"
    assert int(ctx.stat(StatType.FIXED_ARMOR)) == before, \
        "buff permanent erode par le tick : %d -> %d" % (before, int(ctx.stat(StatType.FIXED_ARMOR)))


def test_cursed_plague_bell_extramove_expires_like_waaagh():
    """SECOND membre a timer (#224) : `CursedPlagueBell_ExtraMove` (0x431 = 1073), pose pour UN tour
    sur les amis Chaos de l'aura de Corrodius. Meme croisement R16 x O3 que `Waaagh_ExtraMovement`,
    sur une classe d'effet NATIVE bespoke (`CursedPlagueBell_ExtraMoveEffect$$ApplyInternal` emet son
    propre `ChangeStat(Stat(Movement, Modification), ..., Entity(effect))`) au lieu de la feuille
    generique -- le port doit donc l'attribuer ET le reverter par le MEME canal EAGER."""
    amt = int(ability_var("CursedPlagueBell", "extraMovement", is_constant=True) or 0)
    assert amt, "extraMovement non resoluble en gameconfig -> scenario vide"
    cap = [{"name": "CursedPlagueBell_ExtraMove", "effectType": 1073, "level": 1,
            "remaining": 1, "source": UID}]
    st, ctx = _build(cap, {"movement": amt}, visual="worldJakhal")
    assert int(ctx.stat(StatType.MOVEMENT)) == BASE["movement"] + amt, \
        "le seed ne reproduit pas le Current capte"
    per_source = dict(ctx.stats.components[int(StatType.MOVEMENT)].modification.per_source)
    assert [k for k in per_source if isinstance(k, tuple) and k[:2] == ("statmod", 1073)], \
        "1073 SEEDE non attribue (per_source=%s)" % (per_source,)
    assert int(per_source.get(CAPTURED_SOURCE, 0)) == 0, "residu opaque non nul : %s" % (per_source,)

    EndTurnOperation.execute(st, advance=False)

    assert not st.effects.has_effect(UID, effect_type=1073), "1073 (turns=1) non expire au tick"
    assert int(ctx.stat(StatType.MOVEMENT)) == BASE["movement"], (
        "effet RETIRE mais buff CONSERVE : MOVEMENT=%d au lieu de %d"
        % (int(ctx.stat(StatType.MOVEMENT)), BASE["movement"]))


def test_seed_attribution_survives_the_expiry_path():
    """La condition NECESSAIRE du revert : au seed la contribution vit sous une cle d'effet, pas dans
    le residu opaque. Si elle retombait dans `CAPTURED_SOURCE`, les tests ci-dessus deviendraient
    silencieusement inoperants (rien a retirer, donc rien qui rougit)."""
    st, ctx, amt = _waaagh_state(remaining=1)
    per_source = dict(ctx.stats.components[int(StatType.MOVEMENT)].modification.per_source)
    statmod = [k for k in per_source
               if isinstance(k, tuple) and k[:2] == ("statmod", WAAAGH_EXTRA_MOVEMENT)]
    assert statmod, "stat-mod EAGER seede NON attribue (per_source=%s)" % (per_source,)
    assert sum(per_source[k] for k in statmod) == amt
    assert int(per_source.get(CAPTURED_SOURCE, 0)) == 0, \
        "residu opaque non nul : %s" % (per_source,)


if __name__ == "__main__":                                   # execution directe = mesure lisible
    raise SystemExit(pytest.main([__file__, "-q"]))
