"""#982-r4 -- `KeepOnChangeOwner` : la prise de controle PURGE deux classes d'effet, pas zero, pas toutes.

`IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects` met un effet dans la liste de
SUPPRESSION quand `IEffect` **slot 3** (`get_KeepOnChangeOwner`) rend **FAUX**. Le port ne purgeait
RIEN. Ce fichier garde les quatre points ou une lecture distraite resterait verte ailleurs :

  1. **LE SENS DU TEST.** Le natif retire sur FAUX et garde sur VRAI, et la base rend **VRAI**
     (`b0 01 c3`). Inverser rendrait une purge quasi-generale : **463** effets retires a tort.
  2. **LE DOMAINE, DERIVE et COMPLET.** Exactement **DEUX** classes surchargent, et les deux a
     FAUX. Une derivation par la VTABLE RUNTIME ne peut pas le montrer : IL2CPP ne remplit la
     vtable qu'a l'INITIALISATION, et une session sans taunt ne mesure que **53** classes sur 465
     -- elle rend alors << AUCUN override >>, un **faux zero** qui ferait conclure << rien a
     purger >>. La source qui conclut est le `global-metadata.dat` (qui DECLARE) + les OCTETS du
     corps (qui VALENT).
  3. **LA CASCADE.** Le natif passe par `processor.<slot 0x11>` = `RemoveEffectOperation$$Execute`
     -- donc avec `On(0x3f)`/`On(0x40)`, les reverts et le retrait RECURSIF des enfants. Un port
     qui se contenterait de marquer le parent laisserait les trois sous-effets du taunt en place.
  4. **LES DEUX BOUCLES.** Le domaine est fige AVANT le premier retrait ; filtrer a la volee
     ferait sauter des entrees, puisque le retrait mute la liste du porteur.

TEMOIN NON NUL exige : la fixture pose A LA FOIS un effet purgeable et un effet conserve. Sans les
deux, << purger >> et << ne rien purger >> donneraient le meme observable.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier monte un `State` runner, la factory d'effets complete,
    # les Operations de pose et de retrait, et l'owner-swap -- sa fermeture d'import couvre
    # l'essentiel de `engine/**`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: True` -- l'etage 1 DERIVE le domaine depuis `global-metadata.dat` et les octets du
    # binaire. Un changement de build DOIT le rejouer : c'est precisement ce qu'il garde.
    "build": True,
    # `toujours: False` : l'etage 1 cale le bloc `methodPointers` sur 465 classes (~35 s). Les
    # etages 2 a 4 sont, eux, instantanes.
    "toujours": False,
    "raison": "`IEffect` slot 3 `get_KeepOnChangeOwner` : le DOMAINE des classes purgees a la "
              "prise de controle (2 sur 465, derive offline), le SENS du test, la CASCADE par "
              "`RemoveEffectOperation`, et le fige des deux boucles.",
}

import pytest

from engine.entities.effect_type import EffectType

#: Les DEUX classes NATIVES qui surchargent le getter, et leur homologue PORTE.
#: Mesure : `probe_982r4_keep_on_change_owner.py` -- 465 classes couvertes, 0 INCONNU.
CLASSES_NATIVES_A_FAUX = {
    "IdunBattle.Entities.Effects.TauntedEffect",
    "IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect",
}
PORTS_A_FAUX = {"TauntedEffect", "HolyDuelTauntEffect"}
#: Un effet qui, lui, SURVIT -- le temoin qui rend le fichier non degenere.
TYPE_CONSERVE = EffectType.Stunned
TYPES_PURGES = (EffectType.Taunted_OnlySpecificTargets, EffectType.HolyDuel_Taunt)

POSSEDE, POSSESSEUR = 2, 1


@pytest.fixture(name="etat_avant_prise_de_controle")
def _etat_avant_prise_de_controle():
    """Une unite (team 2) portant DEUX effets purgeables ET un effet conserve, face a un posseur
    (team 1). Les effets sont poses par l'Operation REELLE, donc avec leurs sous-effets."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.stats import UnitStats
    from engine.runner.components import OwnerComponent, StatsComponent
    from engine.runner.operations.effects import AddEffectOperation
    from engine.runner.state import State

    st = State()
    st.effects = EffectsState()
    for uid, team in ((POSSESSEUR, 1), (POSSEDE, 2)):
        ent = st.add_entity(uid)
        us = UnitStats()

        class _Ctx:
            traits = []

            def __init__(self, u):
                self.stats = u

            def get_stat(self, *_a, **_k):
                return 0

        ent.add_component(StatsComponent(ctx=_Ctx(us)))
        ent.add_component(OwnerComponent(team, 2 + team))
    for t in TYPES_PURGES + (TYPE_CONSERVE,):
        AddEffectOperation.execute(st, source=POSSESSEUR, target=POSSEDE,
                                   effect_type=int(t), name=t.name)
    portes = [e.name for e in st.effects.by_unit[POSSEDE]]
    assert any(n == TYPE_CONSERVE.name for n in portes), \
        "regime DEGENERE : il faut un effet CONSERVE, sinon `purger` et `tout purger` se confondent"
    assert any(n == TYPES_PURGES[0].name for n in portes), \
        "regime DEGENERE : il faut un effet PURGEABLE"
    return st


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- LE DOMAINE, DERIVE DU BINAIRE (pieges 1 et 2)
# ---------------------------------------------------------------------------------------------
def test_le_domaine_natif_est_DERIVE_et_vaut_exactement_deux_classes():
    import probe_982r4_keep_on_change_owner as P

    table = P.deriver()
    assert table is not None, "la derivation offline a REFUSE de conclure -- rien n'est devine"
    faux = {k for k, v in table.items() if v.get("valeur_effective") is False}
    inconnu = {k for k, v in table.items() if v.get("valeur_effective") is None}
    base = table.get("IdunBattle.Entities.Effects.BaseEffect", {})
    assert not inconnu, "%d classe(s) INCONNUE(S) : %s" % (len(inconnu), sorted(inconnu)[:5])
    assert base.get("valeur_propre") is True, (
        "piege 1 -- LE SENS DU TEST : la BASE rend VRAI (`b0 01 c3`), donc le defaut est "
        "<< l'effet SURVIT >>. Une base a faux ferait purger 463 effets a tort")
    assert faux == CLASSES_NATIVES_A_FAUX, \
        "le domaine natif a bouge : mesure=%s attendu=%s" % (sorted(faux), sorted(CLASSES_NATIVES_A_FAUX))
    assert len(table) > 400, "temoin : la fermeture transitive doit couvrir des CENTAINES de classes"


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- LE PORT MIRRORE CE DOMAINE, ET RIEN DE PLUS
# ---------------------------------------------------------------------------------------------
def test_le_port_declare_les_MEMES_deux_classes_et_aucune_autre():
    """PERIMETRE DERIVE du registre, jamais une liste ecrite : une allowlist ne pourrait pas
    montrer la classe qu'elle a oubliee."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import EFFECT_CLASSES

    assert BaseEffect.keep_on_change_owner is True, "la base PORTEE doit rendre VRAI, comme le natif"
    a_faux = {c.__name__ for c in set(EFFECT_CLASSES.values())
              if getattr(c, "keep_on_change_owner", True) is False}
    assert a_faux == PORTS_A_FAUX, \
        "les classes PORTEES a faux ont bouge : mesure=%s attendu=%s" % (sorted(a_faux), sorted(PORTS_A_FAUX))


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- L'OPERATION PURGE, et SEULEMENT ce qu'il faut (pieges 3 et 4)
# ---------------------------------------------------------------------------------------------
def test_la_prise_de_controle_PURGE_les_taunts_et_GARDE_le_reste(etat_avant_prise_de_controle):
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation

    st = etat_avant_prise_de_controle
    assert ChangeUnitOwnerOperation.execute(st, POSSEDE, POSSESSEUR) is True
    restants = {e.name for e in st.effects.by_unit[POSSEDE] if not e.consumed}
    partis = {e.name for e in st.effects.by_unit[POSSEDE] if e.consumed}
    for t in TYPES_PURGES:
        assert t.name in partis, "`%s` doit etre PURGE a la prise de controle" % t.name
    assert TYPE_CONSERVE.name in restants, (
        "`%s` n'a AUCUNE surcharge du getter : le natif le GARDE. Le purger serait la faute "
        "symetrique -- et de loin la plus couteuse (463 classes)" % TYPE_CONSERVE.name)


def test_la_purge_passe_par_RemoveEffectOperation_donc_la_CASCADE(etat_avant_prise_de_controle):
    """Piege 3. `TauntedEffect` pose trois sous-effets (`25` / `26` / `1237`). Un port qui
    marquerait seulement le parent les laisserait vivants -- et avec eux le blocage de mouvement
    d'un taunt que le natif vient de retirer."""
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation

    st = etat_avant_prise_de_controle
    enfants = (EffectType.Taunted_BlockMovement, EffectType.Taunted_CantUseAbility,
               EffectType.Taunted_RefreshUnitTurnFinished)
    avant = {e.name for e in st.effects.by_unit[POSSEDE] if not e.consumed}
    for c in enfants:
        assert c.name in avant, "temoin : le sous-effet `%s` doit etre POSE avant le swap" % c.name
    ChangeUnitOwnerOperation.execute(st, POSSEDE, POSSESSEUR)
    apres = {e.name for e in st.effects.by_unit[POSSEDE] if not e.consumed}
    for c in enfants:
        assert c.name not in apres, \
            "le sous-effet `%s` a survecu : la purge n'est pas passee par `remove_effect_instance`" % c.name


def test_le_gate_d_idempotence_reste_PRIORITAIRE(etat_avant_prise_de_controle):
    """Piege 4 bis. `IsOwnerOverridden` court AVANT `RemoveEffects` : un second swap sur une unite
    DEJA possedee ne doit RIEN purger de plus (et surtout pas re-purger apres qu'un effet a ete
    repose)."""
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    from engine.runner.operations.effects import AddEffectOperation

    st = etat_avant_prise_de_controle
    assert ChangeUnitOwnerOperation.execute(st, POSSEDE, POSSESSEUR) is True
    repose = AddEffectOperation.execute(st, source=POSSESSEUR, target=POSSEDE,
                                        effect_type=int(EffectType.Taunted_OnlySpecificTargets),
                                        name=EffectType.Taunted_OnlySpecificTargets.name)
    assert repose is not None, "temoin : l'effet purgeable doit avoir ete REPOSE"
    assert ChangeUnitOwnerOperation.execute(st, POSSEDE, POSSESSEUR) is False, \
        "gate `IsOwnerOverridden` : le 2e swap est refuse"
    assert repose.consumed is False, \
        "le gate court AVANT `RemoveEffects` : rien n'est purge quand le swap est refuse"
