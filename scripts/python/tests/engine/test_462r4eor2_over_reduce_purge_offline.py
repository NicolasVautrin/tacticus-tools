"""#462-r4e-o-r2 -- GARDE OFFLINE : QUI purge l'accumulateur de sur-reduction, et qui ne le purge pas.

#462-r4e-o-r1 avait ecrit que `FillUpStatComponent+0x24` n'est **JAMAIS** remis a zero, au motif que
`IdunBattle.Entities.Components.FillUpStatComponent$$ResetOverReduce` n'a aucun xref de code. La
premiere moitie est vraie (ce symbole n'est jamais appele) ; la conclusion est FAUSSE -- deux autres
methodes de la meme classe ecrivent `this+0x24 = 0` **EN LIGNE**, sans passer par lui :

    IdunBattle.Entities.Components.FillUpStatComponent$$FillUp:
        filled   = Math.Min(amount, CurrentMaximumValue - Current)
        Current += filled
        this[0x24] = 0                          <- EN QUEUE, INCONDITIONNEL
        return filled

    IdunBattle.Entities.Components.FillUpStatComponent$$Initialize:
        this[0x10] = this[0x14] = this[0x18] = initialValue ; this[0x24] = 0

Xrefs de `FillUp` (EXHAUSTIFS, 3 sites) : `IdunBattle.Operations.HealUnitOperation$$Execute`,
`IdunBattle.Operations.RepairUnitOperation$$Execute`,
`IdunBattle.Operations.ResurrectUnitOperation$$SetHealth`.
Xrefs d'`Initialize` : `IdunBattle.Operations.AddUnitOperation$$Execute`,
`IdunBattle.Entities.Factories.UnitFactory$$Build`, `IdunBattle.Entities.Factories.UnitFactory$$InitHealth`.

=> SOIN, REPARATION et RESURRECTION purgent.

⚠ **ET LE REVIVE AUSSI -- ce fichier a d'abord garde le CONTRAIRE, et la mesure live l'a REFUTE**
(#462-r4e-o-r2-r1). La table de trois ecrivains ci-dessus n'etait PAS exhaustive : il en existe un
QUATRIEME, `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier`, dont les branches
`case 0` (Current), `case 2` (Max) et `case 3` (les deux) ecrivent chacune `this[0x24] = 0`. Le
revive y descend par `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` ->
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifiers` ->
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` (XREF **UNIQUE** d'`ApplyModifier`) ->
`case 0`. « `SetHealth` n'appelle ni `FillUp` ni `Initialize` » reste VRAI et ne concluait rien --
exactement le vice que ce fichier reprochait a #462-r4e-o-r1.
La garde du regime « retour a la vie puis attaque » vit desormais dans
`test_462r4eor2r1_purge_au_retour_a_la_vie_offline.py`, adossee a une mesure LIVE.

POURQUOI OFFLINE, et pourquoi c'est le seul endroit ou ca se garde : `over_reduce > 0` implique
`hp == 0` (`Reduce` n'accumule que ce qu'il n'a PAS pu retirer) -- donc une unite MORTE. Le seul
regime ou un porteur VIVANT a un accumulateur non nul est « mort en sur-reduction PUIS retour a la
vie ». Ici on le joue directement, aux memes chiffres que les regimes live de #462-r4e-o, et on ARME
la contre-epreuve sur le foyer unique `HealthComponent.fill_up`.

ASCII only.
"""
from __future__ import annotations

import inspect

import pytest

from engine.runner.state import State
from engine.runner.components import HealthComponent, UnitComponent, UnitFlagsComponent
from engine.runner.operations.heal import HealUnitOperation
from engine.runner.operations.resurrect import ResurrectUnitOperation
from engine.runner.operations.revive import ReviveUnitOperation, post_pending_revive
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.runner.prng import IntBasedMersenneTwister

HP_MAX = 4000
OVER_REDUCE = 8000        # le gaspille d'un coup de 12000 sur une cible a 4000 PV
HP_RETOUR = 1000          # PV au retour a la vie
COUP = 200                # 4 coups de 200 : sans accumulateur, 2 x 1000 n'est JAMAIS atteint
COUPS = 4


def _unite(alive: bool, hp: int = 0, over_reduce: int = OVER_REDUCE):
    """Une unite nue : PV a `hp` sur `HP_MAX`, accumulateur de sur-reduction seme."""
    st = State()
    e = st.add_entity()
    hc = HealthComponent(hp, HP_MAX)
    hc.over_reduce = over_reduce
    e.add_component(hc)
    e.add_component(UnitComponent("cible", alive))
    e.add_component(UnitFlagsComponent())
    uid = next(iter(st.entities))
    return st, uid, hc


class _EffetsCursed:
    """Double de test : la seule surface de `state.effects` que lit `HealUnitOperation.execute`."""

    def __init__(self, cursed: bool):
        self._cursed = cursed

    def has_effect(self, _unit_id, effect_type=None):        # noqa: D102
        return self._cursed


def _salve(hp_depart: int, over_reduce0: int) -> dict:
    """Une attaque de `COUPS` coups degeneres a `COUP`, sur une cible a `hp_depart` PV qui porte
    `over_reduce0`. C'est le consommateur de l'accumulateur : le terme `healthComponent@+0x24` de la
    surcharge d'instance d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`."""
    hd = HitDamage(COUP, COUP)
    return AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(777), hd, hd, 0, False, COUPS, None,
        hp_current=hp_depart, hp_floor=None, over_reduce0=over_reduce0)


# --------------------------------------------------------------------------------------------
# 1. Le foyer : `HealthComponent.fill_up` (mirror 1:1 de `FillUpStatComponent$$FillUp`)
# --------------------------------------------------------------------------------------------

def test_fill_up_purge_meme_quand_il_ne_soigne_RIEN():
    """`this[0x24] = 0` est en QUEUE de `FillUp`, apres le `return`-able mais avant le `return` :
    aucune garde ne le protege. Une cible DEJA PLEINE (donc `filled == 0`) voit quand meme son
    accumulateur purge -- c'est ce qui rend le port fidele sur les early-returns des appelants."""
    hc = HealthComponent(HP_MAX, HP_MAX)
    hc.over_reduce = OVER_REDUCE
    assert hc.fill_up(500) == 0, "cible pleine -> Min(500, max - max) == 0"
    assert hc.over_reduce == 0, "purge INCONDITIONNELLE (queue de FillUp)"


def test_fill_up_est_RELATIF_et_borne_au_plafond():
    """`filled = Min(amount, CurrentMaximumValue - Current)` ; `Current += filled`."""
    hc = HealthComponent(3900, HP_MAX)
    assert hc.fill_up(500) == 100 and hc.hp == HP_MAX


def test_fill_up_no_op_sans_composant_capte():
    """Absence de composant natif, pas une garde inventee : ni mutation ni purge."""
    hc = HealthComponent(None, None)
    hc.over_reduce = OVER_REDUCE
    assert hc.fill_up(500) == 0 and hc.over_reduce == OVER_REDUCE


# --------------------------------------------------------------------------------------------
# 2. Les trois appelants natifs de `FillUp` purgent -- et le revive NON
# --------------------------------------------------------------------------------------------

def test_le_soin_purge_l_accumulateur():
    """`IdunBattle.Operations.HealUnitOperation$$Execute` -> `FillUp`."""
    st, uid, hc = _unite(alive=True, hp=500)
    assert HealUnitOperation.execute(st, uid, uid, 100) == 100
    assert hc.hp == 600 and hc.over_reduce == 0


def test_le_soin_ANNULE_PAR_CURSED_purge_quand_meme():
    """Le natif ne sort PAS sur `EffectType.Cursed(79)` : il calcule `healAmount = cursed ? 0 :
    predicted` et appelle `FillUp` AVEC 0. Le soin ne rend donc rien, mais l'accumulateur EST purge.
    Le port sortait avant `FillUp` -- c'etait la difference observable."""
    st, uid, hc = _unite(alive=True, hp=500)
    st.effects = _EffetsCursed(True)
    assert HealUnitOperation.execute(st, uid, uid, 100) == 0, "Cursed -> aucun PV rendu"
    assert hc.hp == 500, "Cursed -> les PV ne bougent pas"
    assert hc.over_reduce == 0, "mais `FillUp(0)` a bien ete appele -> purge"


def test_la_resurrection_purge_l_accumulateur():
    """`IdunBattle.Operations.ResurrectUnitOperation$$SetHealth` -> `FillUp`. C'est LE site qui mord :
    le resurrect opere TOUJOURS sur une unite morte, donc sur un accumulateur potentiellement non nul."""
    st, uid, hc = _unite(alive=False)
    ResurrectUnitOperation.execute(st, uid, None, HP_RETOUR, immediate_turn=False)
    assert hc.hp == HP_RETOUR and hc.over_reduce == 0


def test_le_REVIVE_purge_AUSSI___par_un_QUATRIEME_ecrivain():
    """⚠ CE TEST ASSERTIONNAIT L'INVERSE, ET LA MESURE LIVE L'A REFUTE (#462-r4e-o-r2-r1).

    `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` n'appelle bien NI `FillUp` NI
    `Initialize` -- et cela ne concluait RIEN : il pose un modificateur
    `{StatType.Health, ModifierType 0, Min(amount, maxHP)}` qui atteint
    `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` `case 0`, lequel ecrit
    `Current` **ET** `this[0x24] = 0`.

    MESURE qui a tranche (`probe_462r4eor2r1_retour_a_la_vie_over_reduce.py --volet revive`,
    victime a 2000 PV, seuil d'overkill 4000, accumulateur porte 59 807 -- facteur 15) : apres un
    revive `TaintedNarthecium` NATIF, l'attaque suivante rend **5** events `Amount`
    `[213, 214, 281, 255, 227]`, pas **1**."""
    st, uid, hc = _unite(alive=False)
    post_pending_revive(st, uid, HP_RETOUR)
    ReviveUnitOperation.execute(st, uid)
    assert hc.hp == HP_RETOUR
    assert hc.over_reduce == 0, "le revive purge AUSSI (`ApplyModifier` case 0)"


# --------------------------------------------------------------------------------------------
# 3. La CONSEQUENCE observable -- ce que l'accumulateur change vraiment
# --------------------------------------------------------------------------------------------

def test_sans_accumulateur_aucun_flag_et_les_QUATRE_coups_emettent():
    """Reference : 4 coups de 200 sur 1000 PV. Le cumul plafonne a 200 + 800 = 1000 < 2 x 1000,
    donc `UnitFlag.Overkilled` n'est JAMAIS pose et les quatre events sortent."""
    r = _salve(HP_RETOUR, 0)
    assert r["per_hit"] == [COUP] * COUPS
    assert r["overkilled"] is False and r["overkill_at_hit"] is None


def test_avec_accumulateur_herite_le_flag_tombe_des_le_PREMIER_coup():
    """Le CONSOMMATEUR de l'accumulateur, garde a l'ETAGE `_run_hits` : une cible qui entre dans une
    attaque avec `+0x24` non nul est marquee `Overkilled` des le premier coup, A PLEINE VIE --
    `accum = 200 + (1000-1000) + 8000` franchit le seuil immediatement, et le SITE (A) supprime tous
    les coups suivants (le coup qui pose le flag emet encore, cf. #462-r4e-o-r1).

    ⚠ Ce test garde la MECANIQUE, pas un regime atteignable : depuis #462-r4e-o-r2-r1 on sait que
    TOUS les retours a la vie purgent (revive compris), donc aucune unite VIVANTE ne porte plus
    d'accumulateur non nul. Il reste load-bearing parce qu'il est le seul a fixer le comportement
    de `_run_hits` sur `over_reduce0 > 0`, que la formule d'`IsOverkill` lit toujours en PLEIN
    REGIME -- a l'INTERIEUR d'une meme attaque, ou l'accumulateur monte coup apres coup."""
    r = _salve(HP_RETOUR, OVER_REDUCE)
    assert r["overkilled"] is True and r["overkill_at_hit"] == 0
    assert r["per_hit"] == [COUP], "un seul event : les coups 2..4 tombent sur le SITE (A)"


def test_resurrect_puis_attaque___PAS_de_flag_premature():
    """Chaine complete cote RESURRECT : mort en sur-reduction -> resurrection -> attaque. La
    resurrection ayant purge, l'attaque suivante se comporte comme sur une cible neuve."""
    st, uid, hc = _unite(alive=False)
    ResurrectUnitOperation.execute(st, uid, None, HP_RETOUR, immediate_turn=False)
    r = _salve(hc.hp, hc.over_reduce)
    assert r["overkilled"] is False and r["per_hit"] == [COUP] * COUPS


def test_revive_puis_attaque___PAS_de_flag_premature_non_plus():
    """Chaine complete cote REVIVE, SYMETRIQUE du resurrect ci-dessus -- et c'est la correction de
    #462-r4e-o-r2-r1 : le revive purge lui aussi (`ApplyModifier` case 0), donc l'attaque qui suit
    se comporte comme sur une cible neuve. Ce test remplace `test_revive_puis_SOIN_puis_attaque`,
    dont la premisse (« le revive n'a pas purge ») etait FAUSSE."""
    st, uid, hc = _unite(alive=False)
    post_pending_revive(st, uid, HP_RETOUR)
    ReviveUnitOperation.execute(st, uid)
    assert hc.over_reduce == 0, "le revive purge"
    r = _salve(hc.hp, hc.over_reduce)
    assert r["overkilled"] is False and r["per_hit"] == [COUP] * COUPS


def test_le_SOIN_reste_le_seul_desamorceur_INTRA_attaque():
    """Le correctif sur `HealUnitOperation` (#462-r4e-o-r2) n'est PAS devenu inerte : un soin purge
    l'accumulateur d'une unite VIVANTE, et le seul regime qui en produit un est desormais
    l'INTERIEUR d'une attaque (un coup ecrete sur une cible a 0 PV qui n'est pas encore drainee).
    On le pose directement ici -- l'etage superieur est garde par `_salve`."""
    st, uid, hc = _unite(alive=True, hp=HP_RETOUR - 1)
    assert hc.over_reduce == OVER_REDUCE, "premisse : accumulateur seme"
    HealUnitOperation.execute(st, uid, uid, 1)
    assert hc.over_reduce == 0, "le soin purge"
    r = _salve(hc.hp, hc.over_reduce)
    assert r["overkilled"] is False and r["per_hit"] == [COUP] * COUPS


# --------------------------------------------------------------------------------------------
# 4. Foyer UNIQUE -- aucun des trois sites ne doit re-implementer la queue de `FillUp`
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fonction, quoi", [
    (HealUnitOperation.execute, "IdunBattle.Operations.HealUnitOperation$$Execute"),
    (ResurrectUnitOperation.execute, "IdunBattle.Operations.ResurrectUnitOperation$$SetHealth"),
])
def test_les_appelants_passent_par_le_foyer_unique(fonction, quoi):
    src = inspect.getsource(fonction)
    assert ".fill_up(" in src, (
        "%s doit appeler `HealthComponent.fill_up` (le mirror de `FillUp`), pas re-ecrire "
        "`hp = ... + filled` a la main -- sinon la purge de `+0x24` se perd en silence" % quoi)


def test_le_repair_passe_aussi_par_le_foyer_unique():
    """`IdunBattle.Operations.RepairUnitOperation$$Execute` -> `FillUp`. Sa gate amont
    (`EntityCanBeRepaired`) et sa prediction dependent d'un etat de bataille reel : le comportement
    est confronte live par `test_repair_execution_live.py`, et c'est le passage par le foyer qui est
    garde ici."""
    from engine.runner.operations.repair import RepairUnitOperation
    src = inspect.getsource(RepairUnitOperation.execute)
    assert ".fill_up(" in src


# --------------------------------------------------------------------------------------------
# 5. CONTRE-EPREUVE -- on retire le correctif au foyer, les gardes ci-dessus doivent MORDRE
# --------------------------------------------------------------------------------------------

def test_contre_epreuve_le_foyer_desarme_fait_TOMBER_les_gardes(monkeypatch):
    """On restaure la queue d'AVANT #462-r4e-o-r2 (`FillUp` qui ne purge pas) et on re-joue les
    memes assertions. Si elles restaient vertes, c'est que le correctif ne serait pas load-bearing --
    et que les tests ci-dessus seraient vacuously vrais."""
    def _fill_up_sans_purge(self, amount):
        if self.hp is None or self.hp_max is None:
            return 0
        filled = min(int(amount), int(self.hp_max) - int(self.hp))
        self.hp = int(self.hp) + filled
        return filled                                   # <- `this[0x24] = 0` RETIRE

    monkeypatch.setattr(HealthComponent, "fill_up", _fill_up_sans_purge, raising=True)

    st, uid, hc = _unite(alive=True, hp=500)
    HealUnitOperation.execute(st, uid, uid, 100)
    assert hc.over_reduce == OVER_REDUCE, "le soin ne purge plus -> la garde du soin doit tomber"

    st, uid, hc = _unite(alive=False)
    ResurrectUnitOperation.execute(st, uid, None, HP_RETOUR, immediate_turn=False)
    assert hc.over_reduce == OVER_REDUCE, "la resurrection ne purge plus"

    # ... et la CONSEQUENCE se voit : une unite ressuscitee redevient marquee des le 1er coup.
    r = _salve(hc.hp, hc.over_reduce)
    assert r["overkilled"] is True and r["overkill_at_hit"] == 0 and r["per_hit"] == [COUP], (
        "sans la purge, le resurrect pose `Overkilled` prematurement -- exactement le bug corrige")


def test_contre_epreuve_le_revive_a_SON_PROPRE_foyer(monkeypatch):
    """Le revive ne passe PAS par `fill_up` -- il passe par `apply_modifier_set_current` (mirror du
    `case 0` d'`ApplyModifier`, ecriture ABSOLUE). Ce test le PROUVE en desarmant l'autre foyer :
    sous `fill_up` non purgeant, le revive purge quand meme. Sans lui, le test du revive ci-dessus
    pourrait passer par accident via le foyer du soin."""
    def _fill_up_sans_purge(self, amount):
        if self.hp is None or self.hp_max is None:
            return 0
        filled = min(int(amount), int(self.hp_max) - int(self.hp))
        self.hp = int(self.hp) + filled
        return filled                                   # <- `this[0x24] = 0` RETIRE

    monkeypatch.setattr(HealthComponent, "fill_up", _fill_up_sans_purge, raising=True)
    st, uid, hc = _unite(alive=False)
    post_pending_revive(st, uid, HP_RETOUR)
    ReviveUnitOperation.execute(st, uid)
    assert hc.over_reduce == 0, (
        "le revive doit purger par SON foyer (`apply_modifier_set_current`), pas par `fill_up`")
