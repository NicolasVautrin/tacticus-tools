"""#462-r4e-o-r2-r1 -- GARDE de ce que la MESURE LIVE a etabli sur le regime « retour a la vie
NATIF puis attaque NATIVE ».

CE QUE LA MESURE A REFUTE. `#462-r4e-o-r2` avait conclu, au seul decompile, que le REVIVE ne purge
PAS `IdunBattle.Entities.Components.FillUpStatComponent+0x24` -- « un QUIRK natif a ne pas
corriger ». Son argument : `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` n'appelle ni
`FillUp` ni `Initialize`, les deux SEULS ecrivains connus du zero. La premisse est vraie ; la
conclusion etait FAUSSE, parce que la table n'etait pas exhaustive -- exactement le vice que -r2
reprochait a -r1.

LE QUATRIEME ECRIVAIN, relu VERBATIM au build `rnca9r7q6c` :

    IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier(this, modifier):
        switch (modifier@+4) {                        // ModifierType
          case 0: this[0x18] = modifier@+8 ;                 this[0x24] = 0 ;  // Current
          case 2: this[0x14] = this[0x10] = modifier@+8 ;    this[0x24] = 0 ;  // Max
          case 3: this[0x10] = this[0x14] = this[0x18] = v ; this[0x24] = 0 ;  // les deux
          case 5/6/9 : ValueModification.Modify / ReverseModification  -- PAS de purge
          case 7/8   : ValueOverride.SetOverride / RemoveOverride      -- PAS de purge
        }

CHAINE du revive, de bout en bout : `ReviveUnitOperation$$SetHealth` construit
`{StatType.Health = 5, ModifierType = 0, Min(amount, GetStat(unit, Health, MAX))}` ->
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifiers` ->
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` (**XREF UNIQUE** d'`ApplyModifier`) ->
`case 0`.

LA MESURE LIVE, et pourquoi elle tranche (`probe_462r4eor2r1_retour_a_la_vie_over_reduce.py`,
board MC1_67, seed 777, victime a 2000 PV -> seuil d'overkill 4000, accumulateur porte 59 807,
soit un facteur 15) :

  volet (a) REVIVE     -- `TaintedNarthecium` (deathRotbone + worldExecutions adjacent) :
      natif `[213, 214, 281, 255, 227]` (5 events) ; hypothese « accumulateur TRANSPORTE » `[213]`.
  volet (b) RESURRECT  -- trait `Ambush` (genesPrimus, `EnvAmbushResurrectAbility`) :
      natif `[1044, 886, 70, 0, 0]` (5 events) ; hypothese « TRANSPORTE » `[1044]`.

Dans les DEUX cas le natif s'aligne sur « accumulateur PURGE », et le port -- avant correctif --
rendait `[213]` sur (a). Les deux voies de purge sont donc distinctes et toutes deux exercees :
`fill_up` (RELATIF, soin/reparation/resurrect) et `apply_modifier_set_current` (ABSOLU, revive).

CE FICHIER EST OFFLINE, ET C'EST DELIBERE : le montage live est dans le probe (il consomme un
runner, une sur-tuerie, un tirage a 75 % et deux tours). Ici on fige les INVARIANTS que la mesure a
etablis, aux chiffres du regime live.

ASCII only.
"""
from __future__ import annotations

import inspect

import pytest

from engine.runner.state import State
from engine.runner.components import HealthComponent, UnitComponent, UnitFlagsComponent
from engine.runner.operations.resurrect import ResurrectUnitOperation, update_flags_on_resurrect
from engine.runner.operations.revive import ReviveUnitOperation, post_pending_revive
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.unit_flag import UnitFlag

# Les chiffres du regime LIVE mesure (cf. en-tete).
HP_VICTIME = 2000          # `--hp-victime 2000` -> seuil d'overkill = 2 x 2000 = 4000
OVER_REDUCE = 59807        # accumulateur observe juste avant la purge, volets (a) ET (b)
COUP = 250                 # `--unit-stat <att2>:Damage=250` ; 5 coups -> cumul 1250 < 4000
COUPS = 5


def _unite(alive: bool, hp: int = 0, over_reduce: int = OVER_REDUCE, hp_max: int = HP_VICTIME):
    st = State()
    e = st.add_entity()
    hc = HealthComponent(hp, hp_max)
    hc.over_reduce = over_reduce
    e.add_component(hc)
    e.add_component(UnitComponent("cible", alive))
    e.add_component(UnitFlagsComponent())
    uid = next(iter(st.entities))
    return st, uid, hc


def _salve(hp_depart: int, over_reduce0: int) -> dict:
    hd = HitDamage(COUP, COUP)
    return AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(777), hd, hd, 0, False, COUPS, None,
        hp_current=hp_depart, hp_floor=None, over_reduce0=over_reduce0)


# --------------------------------------------------------------------------------------------
# 1. Le foyer NEUF -- `apply_modifier_set_current`, mirror du `case 0` d'`ApplyModifier`
# --------------------------------------------------------------------------------------------

def test_le_foyer_ecrit_en_ABSOLU_et_purge():
    """`case 0` : `this[0x18] = modifier@+8` (ABSOLU, pas un `+=`) puis `this[0x24] = 0`."""
    hc = HealthComponent(0, HP_VICTIME)
    hc.over_reduce = OVER_REDUCE
    hc.apply_modifier_set_current(HP_VICTIME)
    assert hc.hp == HP_VICTIME
    assert hc.over_reduce == 0


def test_le_foyer_est_ABSOLU_et_NON_relatif___il_peut_FAIRE_DESCENDRE_les_PV():
    """La difference de FORME avec `fill_up` (relatif, borne au plafond) est ce qui rend les deux
    mirrors NON interchangeables. Sur une unite MORTE (`Current == 0`) ils coincident -- c'est
    pourquoi la confusion etait invisible ; sur une unite vivante, non."""
    hc = HealthComponent(1500, HP_VICTIME)
    hc.apply_modifier_set_current(400)
    assert hc.hp == 400, "ecriture ABSOLUE : `Current = value`, pas `Current += value`"
    autre = HealthComponent(1500, HP_VICTIME)
    assert autre.fill_up(400) == 400 and autre.hp == 1900, "`FillUp` est RELATIF"


def test_les_DEUX_foyers_purgent___et_ce_sont_bien_DEUX_foyers():
    """`fill_up` (queue de `FillUp`) et `apply_modifier_set_current` (`case 0`) sont deux ecrivains
    natifs DISTINCTS du zero. Aucun ne doit etre l'alias de l'autre."""
    a = HealthComponent(0, HP_VICTIME); a.over_reduce = OVER_REDUCE
    b = HealthComponent(0, HP_VICTIME); b.over_reduce = OVER_REDUCE
    a.fill_up(HP_VICTIME)
    b.apply_modifier_set_current(HP_VICTIME)
    assert a.over_reduce == 0 and b.over_reduce == 0
    assert a.hp == b.hp == HP_VICTIME
    assert (HealthComponent.fill_up is not HealthComponent.apply_modifier_set_current)


# --------------------------------------------------------------------------------------------
# 2. Les DEUX retours a la vie purgent -- volets (a) et (b) de la mesure live
# --------------------------------------------------------------------------------------------

def test_volet_a___le_REVIVE_purge():
    """Volet (a) de la mesure : `TaintedNarthecium`. L'unite revient a `Min(amount, maxHP)` PV
    SANS l'accumulateur de sa vie precedente."""
    st, uid, hc = _unite(alive=False)
    post_pending_revive(st, uid, HP_VICTIME)
    ReviveUnitOperation.execute(st, uid)
    assert hc.hp == HP_VICTIME and hc.over_reduce == 0


def test_volet_b___le_RESURRECT_purge():
    """Volet (b) : trait `Ambush`. Meme conclusion, autre voie (`FillUp`)."""
    st, uid, hc = _unite(alive=False)
    ResurrectUnitOperation.execute(st, uid, None, HP_VICTIME, immediate_turn=False)
    assert hc.hp == HP_VICTIME and hc.over_reduce == 0


@pytest.mark.parametrize("retour", ["revive", "resurrect"])
def test_la_CONSEQUENCE_mesuree___cardinalite_PLEINE_apres_le_retour_a_la_vie(retour):
    """L'OBSERVABLE de la mesure live : apres le retour a la vie, l'attaque suivante emet TOUS ses
    events. Si l'accumulateur survivait, `IsOverkill` serait vrai des le coup 0 et le SITE (A)
    supprimerait les suivants -- cardinalite 1. Chiffres du regime live."""
    st, uid, hc = _unite(alive=False)
    if retour == "revive":
        post_pending_revive(st, uid, HP_VICTIME)
        ReviveUnitOperation.execute(st, uid)
    else:
        ResurrectUnitOperation.execute(st, uid, None, HP_VICTIME, immediate_turn=False)
    r = _salve(hc.hp, hc.over_reduce)
    assert len(r["per_hit"]) == COUPS, "cardinalite PLEINE (le natif rend 5 events)"
    assert r["overkilled"] is False and r["overkill_at_hit"] is None


@pytest.mark.parametrize("retour", ["revive", "resurrect"])
def test_le_regime_DISCRIMINE___sans_la_purge_la_cardinalite_tombe_a_UN(retour):
    """Contre-modele NON MUTANT : le meme calcul, avec l'accumulateur laisse en place. S'il rendait
    lui aussi 5 events, le test ci-dessus serait vacuously vrai -- et c'est exactement le controle
    qui manquait a la 1re redaction du probe."""
    r = _salve(HP_VICTIME, OVER_REDUCE)
    assert r["per_hit"] == [COUP], "un seul event : le SITE (A) supprime les coups 2..5"
    assert r["overkilled"] is True and r["overkill_at_hit"] == 0


# --------------------------------------------------------------------------------------------
# 3. Chaque retour a la vie passe par SON foyer -- et pas par celui de l'autre
# --------------------------------------------------------------------------------------------

def test_le_revive_appelle_le_foyer_ABSOLU_et_PAS_fill_up():
    src = inspect.getsource(ReviveUnitOperation.execute)
    assert ".apply_modifier_set_current(" in src, (
        "`ReviveUnitOperation` doit passer par le mirror du `case 0` d'`ApplyModifier`")
    assert ".fill_up(" not in src, (
        "le revive n'appelle PAS `FillUp` -- c'est la seule moitie de #462-r4e-o-r2 qui etait vraie")


def test_le_resurrect_appelle_fill_up_et_PAS_le_foyer_absolu():
    src = inspect.getsource(ResurrectUnitOperation.execute)
    assert ".fill_up(" in src, "`ResurrectUnitOperation$$SetHealth` appelle bien `FillUp`"
    assert ".apply_modifier_set_current(" not in src


def test_contre_epreuve_le_foyer_ABSOLU_desarme_fait_TOMBER_le_volet_a(monkeypatch):
    """On restaure le port d'AVANT #462-r4e-o-r2-r1 (le `case 0` sans sa purge) : le volet (a)
    doit alors rendre la cardinalite 1, c'est-a-dire exactement l'ecart mesure contre le natif."""
    def _sans_purge(self, value):
        self.hp = int(value)                      # <- `this[0x24] = 0` RETIRE

    monkeypatch.setattr(HealthComponent, "apply_modifier_set_current", _sans_purge, raising=True)
    st, uid, hc = _unite(alive=False)
    post_pending_revive(st, uid, HP_VICTIME)
    ReviveUnitOperation.execute(st, uid)
    assert hc.over_reduce == OVER_REDUCE, "mutation active : le revive ne purge plus"
    r = _salve(hc.hp, hc.over_reduce)
    assert r["per_hit"] == [COUP], (
        "sans la purge, le port rend 1 event la ou le natif en rend 5 -- l'ecart MESURE")


# --------------------------------------------------------------------------------------------
# 4. La rafale de flags de `ResurrectUnitOperation$$UpdateFlags` -- `Remove(8)` est LOAD-BEARING
# --------------------------------------------------------------------------------------------

def test_la_resurrection_retire_TOUS_les_flags_de_la_rafale_native():
    """`Remove(6) ; Remove(0xf) ; Remove(8) ; Remove(0x1a) ; Remove(9)`. Le port n'en portait qu'UN
    (`Remove(0x1a)`), et l'omission de `Remove(8 = Overkilled)` laissait une unite ressuscitee
    apres overkill INFRAPPABLE cote port (gate du SITE (A))."""
    fl = UnitFlagsComponent()
    for f in (UnitFlag.Dead, UnitFlag.Downed, UnitFlag.Overkilled, UnitFlag.Removed, UnitFlag.Fled,
              UnitFlag.Moved):
        fl.add(f)
    update_flags_on_resurrect(fl)
    for f in (UnitFlag.Dead, UnitFlag.Downed, UnitFlag.Overkilled, UnitFlag.Removed, UnitFlag.Fled):
        assert not fl.has(f), "Remove(%#x) manquant dans la rafale" % int(f)
    assert fl.has(UnitFlag.Moved), "la rafale ne touche QUE les cinq flags du natif"


def test_le_revive_retire_Overkilled_et_pose_Revived():
    """`ReviveUnitOperation$$Execute` : `Remove(0xf)`, `Remove(8)`, `Add(0x14)`. Mesure live des
    flags de la victime apres revive natif : `[0, 1, 20]` -- le port rendait `[0, 1]`."""
    st, uid, hc = _unite(alive=False)
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    fl.add(UnitFlag.Overkilled)
    fl.add(UnitFlag.Downed)
    post_pending_revive(st, uid, HP_VICTIME)
    ReviveUnitOperation.execute(st, uid)
    assert not fl.has(UnitFlag.Overkilled) and not fl.has(UnitFlag.Downed)
    assert fl.has(UnitFlag.Revived), "Add(0x14) manquant"
