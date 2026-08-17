"""GARDE #433-r3-r2-r1 / #433-r3-r2-r1-r1 / #550-r4-r1 (OFFLINE PURE) -- qui POSE et qui LIT
`UnitFlag.Untargetable`, et a quel RANG le gate `Dead` de `displace.py` mord.

POURQUOI CE FICHIER
-------------------
Trois residus, une seule question de fond, et les trois enonces se sont averes VRAIS -- mais
chacun SOUS-ESTIMAIT son propre ecart.

1. `#433-r3-r2-r1` -- << le port n'inscrit JAMAIS `0x11` >>. Exact, et
   `UnitFlagsComponent` n'avait meme pas le membre. Ce que la fiche ne disait pas : le port a
   DEUX familles de lecteurs, et seule celle qui interroge les EFFETS
   (`aura_selectors.is_targetable`, `ai.state_bridge._is_untargetable`,
   `playbook.adjacency.is_targetable`) fonctionnait. Celle qui interroge le FLAG etait MORTE --
   `abilities/targeting.py::is_targetable` (`= !HasFlag(unit, 0x11)`) le disait dans sa propre
   docstring : << le predicat est constamment vrai offline >>. Or `IsTargetable` a **CINQ**
   appelants natifs (xrefs relues sur `t6dpr4k06g`), dont QUATRE sont portes :
   `TargetingQuery$$GetInvalidTargetReason` (la regle `TargetIsTargetable`),
   `DamageCalculations$$ShouldApplyRangedInMelee`, `DisplaceUnitOperation$$ApplyKnockbackTo`,
   `BattleQuery$$IsTargetInAttackRangeForSummon`.

2. `#433-r3-r2-r1-r1` -- << DEUX Operations posent le flag HORS de tout effet >>. Exact.
   `ResurrectUnitOperation$$Execute` et `AddUnitOperation$$Execute` encadrent chacune leur corps
   d'un `Add(0x11)` ... `Remove(0x11)`. Le bloc d'`AddUnitOperation` que la fiche declarait
   << NON LU >> l'est desormais : il contient `AddUnitOperation$$KillSteppableUnits`, donc
   `KillUnitOperation$$Execute` en entier -- la fenetre n'est PAS morte.

3. `#550-r4-r1` -- << le gate `HasFlag(unit, 6 = Dead)` est au MAUVAIS RANG >>. Exact.
   `DisplaceUnitOperation$$Execute` ne teste la mort NULLE PART ; seul le 2e gate de
   `SetUnitPositionOperation$$Execute` le fait, et il ne saute QUE l'ecriture -- `$$AddTilesMoved`
   et `$$EventAndAbilitiesAndEffects` sont joues juste apres, inconditionnellement.

CE QUE CE FICHIER GRAVE, etage par etage, chacun avec sa CONTRE-EPREUVE dans le meme montage.
Aucun etage ne s'appuie sur un chiffre recopie : les ordinaux sont re-derives de
`data/symbols/<build>/frida/enums.tsv`.

ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                              # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.entities.effects import aura_selectors as _aura                # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.unit_flag import UnitFlag                             # noqa: E402
from engine.runner.abilities import targeting as _targeting                # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,    # noqa: E402
                                      UnitFlagsComponent)
from engine.runner.events import EventBus                                  # noqa: E402
from engine.runner.operations import displace as _displace                 # noqa: E402
from engine.runner.operations import movement as _movement                 # noqa: E402
from engine.runner.operations import resurrect as _resurrect               # noqa: E402
from engine.runner.operations import tile_reservation                      # noqa: E402
from engine.runner.operations.effects import AddEffectOperation            # noqa: E402
from engine.runner.operations.movement import MoveUnitOperation            # noqa: E402
from engine.runner.operations.remove_effects import remove_effect_instance  # noqa: E402
from engine.runner.operations.triggers.dispatch import move_death as _md   # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

DECLENCHEUR = {
    "chemins": (
        # le membre + les deux poseurs/retireurs d'effet
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/operations/remove_effects.py",
        # le domaine et les deux familles de lecteurs
        "scripts/python/engine/entities/effects/aura_selectors.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        # les deux fenetres hors-effet
        "scripts/python/engine/runner/operations/resurrect.py",
        "scripts/python/engine/runner/operations/spawn.py",
        # le rang du gate `Dead`
        "scripts/python/engine/runner/operations/displace.py",
        "scripts/python/engine/runner/operations/movement.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il grave (a) que le canal FLAG est ARME -- il ne l'a jamais ete avant #433-r3-r2-r1 "
              "et rien ne rougissait, (b) que le retrait est NU (pas de comptage de references), "
              "(c) que les deux fenetres hors-effet existent, et (d) que le gate `Dead` du "
              "deplacement force ne saute QUE l'ecriture, jamais la queue.",
}

ROOT = Path(__file__).resolve().parents[4].parent

COLS, ROWS = 7, 7
POUSSEUR, POUSSEE, TEMOIN, MORT = 10, 20, 30, 40

#: Destination du push de reference, **MESUREE et non postulee** : `POUSSEUR` (2,3) pousse
#: `POUSSEE` (3,3) le long de la direction hex pousseur->poussee PROLONGEE, et la table even-q de
#: la parite du pousseur donne `(4,2)`, PAS `(4,3)`. Le nom evite qu'un lecteur << corrige >> ce
#: qui n'est pas une faute -- cf. `project_hexgeo_parity_fix`, ou la parite odd-q avait deja ete
#: inversee par le passe.
DEST_PUSH = (4, 2)

#: Ordinal ATTENDU du flag, FIGE ICI (le mirror seul redeviendrait vert apres un renumerotage --
#: cf. le cran manquant de `probe_313`, CLAUDE.md). Re-derive du build par l'etage 0.
ORDINAL_UNTARGETABLE = 17
#: `EffectType.Untargetable` = la BASE concrete, inscrite au domaine par #433-r3-r2-r1.
ORDINAL_EFFET_UNTARGETABLE = 1044
#: `TitanhammerSquad_TeleportingIn` -- REFUS PROUVE (`IsUntargetableEnabled` surchargee a `false`).
ORDINAL_EFFET_TITANHAMMER = 1573


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _monter_etat(unites) -> "object":
    """FIXTURE NOMMEE ET REUTILISABLE -- montage commun a tous les etages.

    `unites` = iterable de `(id, col, row, team, alive)`. Board 7x7 plat, tout marchable, pas de
    trait. `EffectsState` materialise si `load_state` n'en pose pas (montage sans
    `combatSnapshot.effects`)."""
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "ultraTitus", "alive": bool(alive), "team": team, "owner": team,
         "pos": {"col": col, "row": row}, "effects": []}
        for (uid, col, row, team, alive) in unites]}
    observe = {"units": [{"squadId": uid, "hp": (1000 if alive else 0), "hpMax": 1000}
                         for (uid, _c, _r, _t, alive) in unites]}
    snapshot = {"units": [{"entityId": uid, "entityType": 1,
                           "stats": {"health": (1000 if alive else 0), "movement": 3,
                                     "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": "ultraTitus", "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for (uid, _c, _r, _t, alive) in unites]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    for (uid, _c, _r, _t, alive) in unites:
        ent = st.get_entity(uid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is not None:
            uc.alive = bool(alive)
    return st


@pytest.fixture
def etat_pousse():
    """`POUSSEUR` (2,3) pousse `POUSSEE` (3,3) vers (4,3), libre. `TEMOIN` loin."""
    return _monter_etat([(POUSSEUR, 2, 3, 1, True), (POUSSEE, 3, 3, 2, True),
                         (TEMOIN, 0, 0, 2, True)])


@pytest.fixture
def etat_pousse_mort():
    """Meme geometrie, mais la POUSSEE est un CADAVRE -- le regime de #550-r4-r1."""
    return _monter_etat([(POUSSEUR, 2, 3, 1, True), (POUSSEE, 3, 3, 2, False),
                         (TEMOIN, 0, 0, 2, True)])


def _flags(st, uid) -> UnitFlagsComponent:
    ent = st.get_entity(uid)
    fl = ent.get_component(UnitFlagsComponent)
    if fl is None:
        fl = ent.add_component(UnitFlagsComponent())
    return fl


def _poser(st, uid, effect_type, nom):
    return AddEffectOperation.execute(st, source=uid, target=uid,
                                      effect_type=int(effect_type), name=nom)


# ===================================================== etage 0 : les ordinaux, RE-DERIVES du build

def _enums_du_build() -> "dict | None":
    d = ROOT / "data" / "symbols"
    cur = d / "CURRENT"
    if not cur.exists():
        return None
    build = cur.read_text(encoding="utf-8").strip()
    tsv = d / build / "frida" / "enums.tsv"
    if not tsv.exists():
        return None
    out = {}
    for ligne in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\t" not in ligne:
            continue
        cle, corps = ligne.split("\t", 1)
        membres = {}
        for morceau in corps.split(","):
            if "=" in morceau:
                v, n = morceau.split("=", 1)
                try:
                    membres[n.strip()] = int(v)
                except ValueError:
                    pass
        out[cle] = membres
    return out


def test_etage0_les_trois_ordinaux_sont_ceux_du_build():
    """L'ordinal ECRIT AU SITE est fige ici, pas seulement dans le mirror : un mirror regenere
    apres renumerotage redeviendrait vert alors que la constante du site aurait change."""
    enums = _enums_du_build()
    if not enums:
        pytest.skip("aucune table `frida/enums.tsv` pour le build courant")
    uf = enums.get("IdunBattle.Entities.Enum.UnitFlag") or {}
    et = enums.get("IdunBattle.Entities.Enum.EffectType") or {}
    assert uf, "table `UnitFlag` VIDE -- l'etage ne mesure rien (garde de non-vacuite)"
    assert et, "table `EffectType` VIDE -- l'etage ne mesure rien (garde de non-vacuite)"
    assert uf.get("Untargetable") == ORDINAL_UNTARGETABLE == int(UnitFlag.Untargetable), (
        f"`UnitFlag.Untargetable` : build={uf.get('Untargetable')} "
        f"mirror={int(UnitFlag.Untargetable)} site={ORDINAL_UNTARGETABLE}")
    assert int(UnitFlagsComponent.UNTARGETABLE) == ORDINAL_UNTARGETABLE, (
        "`UnitFlagsComponent.UNTARGETABLE` ne pointe pas le membre d'enum")
    assert et.get("Untargetable") == ORDINAL_EFFET_UNTARGETABLE == int(EffectType.Untargetable)
    assert et.get("TitanhammerSquad_TeleportingIn") == ORDINAL_EFFET_TITANHAMMER


# ============================== etage 1 : le DOMAINE -- 1044 dedans, 1573 dehors (refus PROUVE)

def test_etage1_le_domaine_contient_1044_et_exclut_1573():
    dom = {int(t) for t in _aura.UNTARGETABLE_EFFECT_TYPES}
    assert dom, "domaine VIDE -- l'etage ne mesure rien"
    assert ORDINAL_EFFET_UNTARGETABLE in dom, (
        "`1044 Untargetable` -- la BASE CONCRETE d'`UntargetableEffect`, posee ET retiree dans le "
        "meme arbre DSL par `KissOfDeath` et `WallOfMirrors` -- n'est pas dans le domaine")
    assert ORDINAL_EFFET_TITANHAMMER not in dom, (
        "`1573 TitanhammerSquad_TeleportingIn` est REVENU dans le domaine : sa classe surcharge "
        "`IsUntargetableEnabled` avec `32 c0 c3` = false, donc `$$ApplyInternal` sort AVANT le "
        "`UnitFlagsComponent$$Add`. L'inscrire produit une divergence RESTRICTIVE")


# =========================== etage 2 : LA POSE -- `UntargetableEffect$$ApplyInternal`, canal FLAG

def test_etage2_la_pose_d_un_effet_du_domaine_inscrit_le_flag(etat_pousse):
    """C'EST L'ETAGE QUI ETAIT ROUGE AVANT #433-r3-r2-r1 -- aucun chemin du port n'inscrivait
    `0x11`, et rien ne le signalait."""
    st = etat_pousse
    assert not _flags(st, POUSSEE).has(UnitFlagsComponent.UNTARGETABLE), "etat initial pollue"
    eff = _poser(st, POUSSEE, EffectType.Untargetable, EffectType.Untargetable.name)
    assert eff is not None, "la pose a ete refusee -- le montage ne mesure rien"
    assert _flags(st, POUSSEE).has(UnitFlagsComponent.UNTARGETABLE), (
        "`AddEffectOperation` n'inscrit pas `UnitFlag.Untargetable` : la part "
        "`_apply_untargetable_flag` (mirror `UntargetableEffect$$ApplyInternal`) ne mord pas")


def test_etage2bis_un_effet_HORS_domaine_n_inscrit_RIEN(etat_pousse):
    """CONTRE-EPREUVE de l'etage 2 : sans elle, une part qui poserait le flag INCONDITIONNELLEMENT
    passerait pour verte."""
    st = etat_pousse
    _poser(st, POUSSEE, EffectType.Pinned, EffectType.Pinned.name)
    assert not _flags(st, POUSSEE).has(UnitFlagsComponent.UNTARGETABLE), (
        "`Pinned` n'appartient PAS a la fermeture d'`UntargetableEffect` et pose pourtant le flag "
        "-- le gate de domaine de `_apply_untargetable_flag` ne mord pas")


# ================== etage 3 : LE CANAL COMBAT -- `UnitExtensions$$IsTargetable`, enfin non constant

def test_etage3_le_canal_COMBAT_voit_le_flag(etat_pousse):
    """`abilities/targeting.py::is_targetable` etait CONSTANTEMENT VRAI (sa propre docstring le
    disait). Il a QUATRE consommateurs portes ; cet etage garde qu'il n'est plus constant."""
    st = etat_pousse
    assert _targeting.is_targetable(st, POUSSEE) is True, "temoin AVANT la pose"
    _poser(st, POUSSEE, EffectType.Untargetable, EffectType.Untargetable.name)
    assert _targeting.is_targetable(st, POUSSEE) is False, (
        "le canal COMBAT reste aveugle au flag -- toute la regle `TargetIsTargetable` d'"
        "`ActiveAbilityOperation$$IsInvalidTarget` est donc encore morte")
    assert _targeting.is_targetable(st, TEMOIN) is True, (
        "le TEMOIN devient non ciblable : le predicat ne lit pas l'unite qu'on lui passe")


# ======================= etage 4 : LE RETRAIT -- `$$RevertInternal`, tail call NU, SANS refcount

def test_etage4_le_retrait_est_NU_et_ne_compte_pas_les_references(etat_pousse):
    """QUIRK NATIF PORTE TEL QUEL. `UntargetableEffect$$RevertInternal` est un TAIL CALL vers
    `UnitFlagsComponent$$Remove(0x11)` : aucun gate, aucun comptage. Deux effets du domaine
    partagent UN element d'`OrderedSet`, donc le PREMIER retrait rend l'unite ciblable."""
    st = etat_pousse
    e1 = _poser(st, POUSSEE, EffectType.Untargetable, EffectType.Untargetable.name)
    e2 = _poser(st, POUSSEE, EffectType.TeleportStrike_TeleportingIn,
                EffectType.TeleportStrike_TeleportingIn.name)
    assert e1 is not None and e2 is not None, (
        "le montage a DEUX effets du domaine n'a pas pris -- l'etage serait DEGENERE "
        "(un seul effet ne peut pas montrer l'absence de comptage)")
    assert _flags(st, POUSSEE).has(UnitFlagsComponent.UNTARGETABLE)
    remove_effect_instance(st, POUSSEE, e1)
    assert not _flags(st, POUSSEE).has(UnitFlagsComponent.UNTARGETABLE), (
        "le flag survit au PREMIER retrait : le port a introduit un comptage de references que "
        "`$$RevertInternal` n'a pas")
    # ... et le canal EFFET, lui, dit toujours << non ciblable >> : c'est la divergence NOMMEE
    # (#433-r5), et elle est GRAVEE ici plutot que laissee a la surprise.
    assert _aura.is_targetable(st, POUSSEE) is False, (
        "le canal EFFET devrait encore voir `1035` actif -- si ce n'est plus le cas, la "
        "divergence #433-r5 a change de forme et le OU de `selection_ok_from_ctx` avec elle")


# ============ etage 5 : `ApplyKnockbackTo` -- l'un des CINQ appelants natifs d'`IsTargetable`

def test_etage5_le_knockback_refuse_une_cible_non_ciblable(etat_pousse):
    """`DisplaceUnitOperation$$ApplyKnockbackTo` ouvre sur
    `if (!doIt || !IsTargetable(target)) return;`. Le port l'approximait par << vivant >>."""
    st = etat_pousse
    bus = EventBus()
    assert _displace._apply_knockback_to(st, bus, POUSSEUR, POUSSEE) is not None, (
        "TEMOIN : sans le flag, le knockback DOIT s'appliquer -- sinon l'etage ne mesure rien")
    st2 = _monter_etat([(POUSSEUR, 2, 3, 1, True), (POUSSEE, 3, 3, 2, True)])
    _poser(st2, POUSSEE, EffectType.Untargetable, EffectType.Untargetable.name)
    assert _displace._apply_knockback_to(st2, EventBus(), POUSSEUR, POUSSEE) is None, (
        "le knockback s'applique a une cible NON CIBLABLE -- le gate `IsTargetable` du natif "
        "n'est pas joue")


# ======= etage 6 : LA FENETRE DE RESURRECTION -- `ResurrectUnitOperation$$Execute` (#433-r3-r2-r1-r1)

def test_etage6_la_resurrection_encadre_son_corps_du_flag(monkeypatch):
    """`Add(0x11)` ... `KillSteppableUnits` ... `Remove(0x11)`, HORS de tout effet. La sonde
    remplace le crush -- l'etage mesure le RANG, pas le crush.

    ⚠ Le patch vise `engine.runner.operations.resurrect._kill_steppable_units` et NON le foyer
    `movement`: `resurrect.py` l'importe en FORME A (`from .movement import ...`), donc patcher
    `movement` NE MORDRAIT PAS (CLAUDE.md, HISSER EN FORME B)."""
    st = _monter_etat([(MORT, 3, 3, 1, False), (TEMOIN, 0, 0, 2, True)])
    vu = {}

    def _sonde(state, coord, killer_id):
        vu["pendant"] = _flags(state, MORT).has(UnitFlagsComponent.UNTARGETABLE)
        return []

    monkeypatch.setattr(_resurrect, "_kill_steppable_units", _sonde)
    res = _resurrect.ResurrectUnitOperation.execute(st, MORT, (4, 3), 1000, immediate_turn=False)
    assert res is not None, (
        "la resurrection a ete refusee par un gate amont -- l'etage ne mesure RIEN "
        "(la sonde n'a pas ete atteinte)")
    assert vu.get("pendant") is True, (
        "le flag `UnitFlag.Untargetable` n'est PAS pose pendant `KillSteppableUnits` : la fenetre "
        "d'intouchabilite de `ResurrectUnitOperation$$Execute` n'est pas portee")
    assert not _flags(st, MORT).has(UnitFlagsComponent.UNTARGETABLE), (
        "le flag survit a la resurrection : le `Remove(0x11)` de queue n'est pas joue, l'unite "
        "reste non ciblable POUR LE RESTE DE LA BATAILLE")


def test_etage6bis_la_fenetre_survit_a_une_exception_du_crush(monkeypatch):
    """CONTRE-EPREUVE du `try/finally`. Sans lui, le mode de defaillance est une unite
    definitivement non ciblable -- exactement ce que #1074 a nomme."""
    st = _monter_etat([(MORT, 3, 3, 1, False), (TEMOIN, 0, 0, 2, True)])

    def _explose(state, coord, killer_id):
        raise RuntimeError("crush en echec (contre-epreuve)")

    monkeypatch.setattr(_resurrect, "_kill_steppable_units", _explose)
    with pytest.raises(RuntimeError):
        _resurrect.ResurrectUnitOperation.execute(st, MORT, (4, 3), 1000, immediate_turn=False)
    assert not _flags(st, MORT).has(UnitFlagsComponent.UNTARGETABLE), (
        "le flag reste pose apres une exception : la fenetre n'est pas sous `try/finally`")


# ======================= etage 7 : LA FENETRE DE SPAWN -- `AddUnitOperation$$Execute`, par AST

def test_etage7_le_spawn_encadre_son_crush_du_flag_sous_finally():
    """GARDE STRUCTURELLE, et elle est ASSUMEE COMME TELLE : monter un spawn complet demanderait
    un `summon_context` gameconfig, hors de ce qu'un test offline pur doit porter. On grave donc
    ce qui est verifiable sans lui -- que `spawn.py` pose le flag, que le retrait est dans un
    `finally`, et que le crush est DEDANS."""
    src = (ROOT / "scripts" / "python" / "engine" / "runner" / "operations"
           / "spawn.py").read_text(encoding="utf-8")
    arbre = ast.parse(src)
    finallys = [n for n in ast.walk(arbre) if isinstance(n, ast.Try) and n.finalbody]
    trouve = []
    for t in finallys:
        corps = ast.dump(ast.Module(body=t.body, type_ignores=[]))
        fin = ast.dump(ast.Module(body=t.finalbody, type_ignores=[]))
        if "_kill_steppable_units" in corps and "UNTARGETABLE" in fin:
            trouve.append(t)
    assert len(trouve) == 1, (
        f"{len(trouve)} bloc(s) `try/finally` de `spawn.py` encadrent `_kill_steppable_units` "
        "d'un retrait d'`UNTARGETABLE` (attendu 1) -- la fenetre d'`AddUnitOperation$$Execute` "
        "n'est plus portee, ou elle l'est deux fois")
    assert "UnitFlagsComponent.UNTARGETABLE" in src, (
        "aucune POSE du flag dans `spawn.py` : le `finally` retirerait un flag jamais pose")


# ========== etage 8 : #550-r4-r1 -- le gate `Dead` ne saute QUE l'ecriture, jamais la QUEUE

def test_etage8_une_cible_MORTE_ne_bouge_pas_mais_la_queue_est_JOUEE(etat_pousse_mort, monkeypatch):
    """LE CoeUR DE #550-r4-r1. `DisplaceUnitOperation$$Execute` ne teste la mort nulle part ; le
    2e gate de `SetUnitPositionOperation$$Execute` refuse l'ECRITURE, puis `$$AddTilesMoved` et
    `$$EventAndAbilitiesAndEffects` sont joues. Le `return` sec de tete n'emettait RIEN."""
    st = etat_pousse_mort
    appels = []
    monkeypatch.setattr(_md, "displace_triggers",
                        lambda state, a, t: appels.append((a, t)) or [])
    res = _displace.DisplaceUnitOperation(POUSSEUR, POUSSEE).execute(st, EventBus())
    pos = st.get_entity(POUSSEE).get_component(PositionComponent)
    assert (pos.col, pos.row) == (3, 3), (
        "le CADAVRE a ete DEPLACE : le gate S2 (`HasFlag(unit, 6 = Dead)`) de "
        "`SetUnitPositionOperation$$Execute` ne refuse plus l'ecriture")
    # L'ASSERTION DE LA QUEUE VIENT AVANT CELLE DU LIBELLE, et c'est deliberé : c'est ELLE que le
    # residu accuse. Dans l'autre ordre, l'arbre d'avant le fix rougissait sur
    # `{'moved': False, 'reason': 'dead'}` -- un libelle -- au lieu de rougir sur l'absence des
    # trois vecteurs, qui est le fait.
    assert appels == [(POUSSEUR, POUSSEE)], (
        "`EventAndAbilitiesAndEffects` n'est PAS joue sur une cible morte : le gate `alive` de "
        "tete est revenu, et avec lui l'abandon de TOUTE l'operation "
        f"(appels observes : {appels!r})")
    assert res.get("moved") is False and res.get("reason") == "set-position-unit-dead", (
        f"le resultat n'impute pas le refus au bon gate : {res!r}")


def test_etage8bis_un_push_BLOQUE_ne_joue_PAS_la_queue(monkeypatch):
    """CONTRE-EPREUVE de discrimination : la sonde de l'etage 8 doit pouvoir rendre << aucun
    appel >>. Sans elle, un `displace_triggers` appele inconditionnellement passerait pour vert.
    Ici la destination sort du plateau -> `FindTileToPush` vide -> le natif `return
    ApplyKnockbackTo(...)`, sans queue."""
    st = _monter_etat([(POUSSEUR, 5, 3, 1, True), (POUSSEE, 6, 3, 2, True)])
    appels = []
    monkeypatch.setattr(_md, "displace_triggers",
                        lambda state, a, t: appels.append((a, t)) or [])
    res = _displace.DisplaceUnitOperation(POUSSEUR, POUSSEE).execute(st, EventBus())
    assert res.get("moved") is False and res.get("reason") == "blocked"
    assert appels == [], (
        f"la queue est jouee sur un push BLOQUE, que le natif abandonne : {appels!r}")


def test_etage8ter_une_cible_VIVANTE_bouge_et_joue_la_queue(etat_pousse, monkeypatch):
    """TEMOIN NON DEGENERE : le regime nominal doit rester nominal. Sans lui, un port qui
    refuserait TOUT deplacement passerait les deux etages precedents."""
    st = etat_pousse
    appels = []
    monkeypatch.setattr(_md, "displace_triggers",
                        lambda state, a, t: appels.append((a, t)) or [])
    res = _displace.DisplaceUnitOperation(POUSSEUR, POUSSEE).execute(st, EventBus())
    pos = st.get_entity(POUSSEE).get_component(PositionComponent)
    assert res.get("moved") is True and (pos.col, pos.row) == DEST_PUSH, (
        f"le push nominal ne deplace plus : {res!r} pos={(pos.col, pos.row)}")
    assert appels == [(POUSSEUR, POUSSEE)]


# ===== etage 9 : #550-r4-r1 volet 2 -- le stand-in ne joue NI `On(PreUnitMove)` NI la reservation

def test_etage9_le_stand_in_de_SetUnitPosition_n_emet_PAS_PreUnitMove(etat_pousse, monkeypatch):
    """`SetUnitPositionOperation$$Execute` relu VERBATIM : il n'appelle le publieur d'evenements
    AUCUNE fois et ne reserve rien. Le port emettait `On(PreUnitMove = 0x1f)` a chaque push /
    pull / switch / Direct -- un vecteur FANTOME dont `HatefulAssaultAbility` (l'attaque
    d'opportunite) est le consommateur le plus visible."""
    st = etat_pousse
    vus = []
    monkeypatch.setattr(_md, "pre_move_triggers",
                        lambda state, uid, dest_tile=None: vus.append(uid) or [])
    _displace.DisplaceUnitOperation(POUSSEUR, POUSSEE).execute(st, EventBus())
    assert vus == [], (
        f"le push a emis `On(PreUnitMove)` pour {vus!r} -- vecteur FANTOME : le natif passe par "
        "`SetUnitPosition`, qui n'emet AUCUN evenement")
    assert not tile_reservation.is_tile_reserved(st, DEST_PUSH), (
        "le stand-in a laisse une reservation sur la destination : `SetReservation` appartient a "
        "`MoveUnitOperation`, pas a `SetUnitPositionOperation`")


def test_etage9bis_un_VRAI_MoveUnitOperation_emet_bien_PreUnitMove(etat_pousse, monkeypatch):
    """CONTRE-EPREUVE : sans elle, un `pre_move_triggers` casse (jamais appele nulle part) rendrait
    l'etage 9 vert pour la mauvaise raison."""
    st = etat_pousse
    vus = []
    monkeypatch.setattr(_md, "pre_move_triggers",
                        lambda state, uid, dest_tile=None: vus.append(uid) or [])
    MoveUnitOperation(POUSSEE, (4, 3)).execute(st, EventBus())
    assert vus == [POUSSEE], (
        f"un `MoveUnitOperation` NOMINAL n'emet plus `On(PreUnitMove)` : {vus!r}")


# ================================ etage 10 : la MUTATION adversariale du gate S2

def test_etage10_desarmer_S2_fait_bouger_le_cadavre(etat_pousse_mort, monkeypatch):
    """CONTRE-EPREUVE PAR MUTATION REELLE du fix : on neutralise `_set_position_unit_is_dead` et
    le port DOIT alors deplacer le cadavre. Si l'assertion de l'etage 8 tenait encore sous cette
    mutation, c'est qu'elle ne mesurait pas S2."""
    st = etat_pousse_mort
    monkeypatch.setattr(_movement, "_set_position_unit_is_dead", lambda state, uid: False)
    _displace.DisplaceUnitOperation(POUSSEUR, POUSSEE).execute(st, EventBus())
    pos = st.get_entity(POUSSEE).get_component(PositionComponent)
    assert (pos.col, pos.row) == DEST_PUSH, (
        "S2 DESARME et le cadavre ne bouge toujours pas : un AUTRE gate le refuse, donc l'etage 8 "
        "ne mesurait pas ce qu'il annonce")
