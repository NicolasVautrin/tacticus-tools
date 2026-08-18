"""#889-r10 -- LE COLLAPSE MONO-CIBLE ET `SelectActor` RESOLVENT LE DOMAINE TUILE, comme le natif.

RE (decompile = verite, build `t6dpr4k06g`). Le residu declarait NON LU « ce que `SelectSingle(
entities, 8)` fait d'une entite TUILE ». Le slot 8 d'`ITargetsSelector` n'est pas un
« SelectSingle » (aucun symbole de ce nom n'existe) : c'est `SelectActor`, et sa chaine est LUE
jusqu'au bout.

`IdunBattle.DSL.TargetsSelector$$SelectActor(this, entities, selectionType)` :

    foreach (entity in this.<slot 23 = Select>(entities)) {
        if (entity == null) continue;
        unit = TargetsSelector.SelectUnit(this, entity, selectionType);
        if (unit != null) return unit;
        if (EntityExtensions.IsMachine(entity)) return entity;
    }
    return null;

`IdunBattle.DSL.TargetsSelector$$SelectUnit(this, entity, selectionType)` -- surcharge ENTITE :

    if (EntityExtensions.IsUnitFoot(entity) || EntityExtensions.IsTile(entity))
        entity = UnitExtensions.GetUnit(entity, this.<+0x10 = State>);
    return (entity != null && IsUnit(entity)
            && MatchesUnitSelectionType(entity, selectionType, State)) ? entity : null;

=> UNE TUILE RESOUT EN SON OCCUPANT. Corrobore par un SECOND etage independant :
`IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer` porte une branche `<TileEntity> ->
UnitExtensions.GetUnit(entity, state) -> RECURSION`. Le camp compare par `AreFriends` est donc celui
de l'OCCUPANT, jamais celui de la tuile.

Meme forme cote ATTAQUE : `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$Execute` (et son
jumeau `AbilityDamageBehaviour$$Execute`) n'a AUCUNE branche mono/multi -- il applique
`UnitExtensions$$GetUnit` a CHAQUE entite rendue par `Select`, et saute la cible quand le resultat
est nul (operation `0x25`, tag `0xa1`).

CE QUE CE FICHIER GARDE, PAR MESURE ET AVEC SON CONTRE-CAS INTEGRE :
  (1) le collapse MONO-cible d'`AttackWithAttackDamage` frappe l'occupant d'une entite-TUILE --
      la ou l'ancien corps (`dsl.base.resolve_unit`, le PREMIER dict) rendait `None`, donc
      `targets = []` : aucune emission, aucune mutation, aucune erreur ;
  (2) meme mesure sur le jumeau `AttackWithAbilityDamage` ;
  (3) `_select_actor` rend l'OCCUPANT d'une tuile, donc `AreEnemies(Owner, <tuile>)` rend FAUX sur
      un ALLIE -- la ou l'ancien corps rendait VRAI (operande nul -> `AreFriends` faux ->
      `AreEnemies`, negation NUE, VRAI POUR TOUT OCCUPANT). C'est la degradation PERMISSIVE que le
      residu nommait ;
  (4) le TEMOIN qui rend la mesure non degeneree : sur un ENNEMI, les deux regimes s'accordent --
      donc c'est bien le camp de l'occupant qui est mesure, pas la presence d'un occupant ;
  (5) UNE SEULE evaluation du selecteur dans le collapse (un selecteur peut consommer le PRNG).

ASCII only. OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

# Declencheur (#486-r15) : fichier PUREMENT offline et structurel. Il monte un `State`, un `Board`
# et des behaviours en memoire, et n'ouvre AUCUN chemin (`open`, `read_text`, `Path`, `rglob` :
# zero occurrence). Sa seule entree hors-code est le gameconfig lu par `profile_pierce` a travers
# `AttackWithAbilityDamage`, et ce chemin-la est SUBSTITUE ici (l'operation de degat est stubbee) :
# la mesure ne depend donc d'aucune donnee de build. Sa fermeture d'imports tient dans la cascade
# derivee de ses foyers (`runner/abilities/behaviours/combat.py`, `entities/triggers.py`), qu'il ne
# faut PAS re-declarer (#531).
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": False,
    "raison": (
        "Fichier PUREMENT offline et PUREMENT structurel : il monte un State/Board en memoire, "
        "substitue les operations de degat et compare des resolutions de cible. Il n'ouvre aucun "
        "chemin et ne lit ni le binaire ni `data/symbols/**`. `chemins` vide est le resultat, pas "
        "un aveu."
    ),
}

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from dataclasses import replace                                             # noqa: E402

from engine.dsl.base import Const, DslContext, resolve_unit                 # noqa: E402
from engine.dsl.effects import ExecutionContext                             # noqa: E402
from engine.entities.pathfinding.board import Board                         # noqa: E402
from engine.entities import triggers as T                                   # noqa: E402
from engine.entities.triggers import AreEnemies, AreFriends                 # noqa: E402
from engine.runner.abilities.behaviours import combat as C                  # noqa: E402
from engine.runner.components import UnitComponent                          # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation           # noqa: E402
from engine.runner.state import State                                       # noqa: E402


# --------------------------------------------------------------------------------------------
# Montage : un plateau 3x1, un caster en (0,0), un occupant en (1,0).
# --------------------------------------------------------------------------------------------
TUILES = [{"id": 500 + i, "col": i, "row": 0, "walkable": True, "elevation": 0,
           "neighbours": [500 + j for j in range(3) if j != i]} for i in range(3)]
TUILE_OCCUPEE = 501                       # (1,0)
TUILE_VIDE = 502                          # (2,0)


class _SelBrut:
    """Selecteur qui rend TEL QUEL ce qu'on lui donne -- la forme `ActiveTarget@+0x68` BRUT, c'est-
    a-dire l'element courant d'un `Foreach` sur des TUILES. Il COMPTE ses evaluations : le collapse
    ne doit en faire qu'UNE (un selecteur reel peut consommer le PRNG)."""

    def __init__(self, valeur):
        self.valeur, self.evaluations = valeur, 0

    def evaluate(self, entities):
        self.evaluations += 1
        return self.valeur

    def select(self, entities):
        return self.evaluate(entities)


def _monde(equipe_occupant: int):
    """`State` + `DslContext` : caster d'equipe 1 en (0,0), occupant d'`equipe_occupant` en (1,0)."""
    st = State()
    st.board = Board(TUILES)
    ids = []
    for vis in ("caster", "occupant"):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        ids.append(e.id)
    # `hp`/`hpMax` sont LOAD-BEARING : `dsl.base._is_alive` (donc `_occupants_by_tile`) exige
    # `hp > 0` -- un dict sans sante est MORT, et l'index d'occupation serait VIDE. Le test
    # rendrait alors « pas d'occupant » au lieu de mesurer la resolution.
    caster = {"id": ids[0], "team": 1, "player": 1, "alive": True, "hp": 100, "hpMax": 100,
              "pos": {"col": 0, "row": 0}, "feet": [(0, 0)]}
    occupant = {"id": ids[1], "team": equipe_occupant, "player": equipe_occupant, "alive": True,
                "hp": 100, "hpMax": 100,
                "pos": {"col": 1, "row": 0}, "feet": [(1, 0)]}
    ctx = DslContext(units=[caster, occupant], caster=caster, target=occupant,
                     owner=caster, board=st.board)
    return st, ctx, caster, occupant


def _stub_degat(monkeypatch):
    """Substitue les DEUX operations de degat : ce fichier mesure la RESOLUTION DE CIBLE, pas un
    montant. Patcher l'attribut de CLASSE mord quelle que soit la forme d'import du module."""
    vus = []

    def _fake(state, attacker_id, target_id, *a, **k):
        vus.append(int(target_id))
        return {"total": 1, "did_crit": False, "did_block": False}

    monkeypatch.setattr(AttackDamageOperation, "execute_ability_attack", staticmethod(_fake))
    monkeypatch.setattr(AttackDamageOperation, "execute_normal_like", staticmethod(_fake))
    monkeypatch.setattr(AttackDamageOperation, "execute_direct", staticmethod(_fake))
    # `profile_pierce` lit le gameconfig : on le neutralise pour que ce fichier ne depende d'AUCUNE
    # entree de build (cf. `DECLENCHEUR`). Liaison de FORME A au niveau module -> patcher l'attribut
    # de `combat` MORD.
    monkeypatch.setattr(C, "profile_pierce", lambda *a, **k: 0)
    return vus


# --------------------------------------------------------------------------------------------
# (1) et (5) -- le collapse mono-cible d'`AttackWithAttackDamage`
# --------------------------------------------------------------------------------------------
def test_collapse_mono_cible_frappe_l_occupant_d_une_entite_TUILE(monkeypatch):
    """`AttackDamageBehaviour$$Execute` applique `UnitExtensions$$GetUnit` a CHAQUE entite. Un
    selecteur a domaine TUILE passe en mono-cible doit donc frapper l'OCCUPANT."""
    st, ctx, _caster, occupant = _monde(equipe_occupant=2)
    sel = _SelBrut([TUILE_OCCUPEE])
    vus = _stub_degat(monkeypatch)
    feuille = C.AttackWithAttackDamage(sel, "Whatever", "Bolter", multi=False,
                                       amount=Const(100), hits=1)
    ectx = ExecutionContext(state=st, rng=st.rng)
    feuille.execute(ctx, ectx)
    assert vus == [occupant["id"]], (
        "le collapse mono-cible doit resoudre la TUILE en son occupant : %r" % (vus,))
    emis = [n for n, _p in ectx.emitted if n == "AttackWithAttackDamage"]
    assert len(emis) == 1, ectx.emitted
    # (5) UNE SEULE evaluation -- un selecteur reel peut consommer le PRNG (`Randomize`).
    assert sel.evaluations == 1, sel.evaluations


def test_CONTRE_CAS_l_ancien_collapse_ne_frappait_RIEN_et_ne_disait_RIEN(monkeypatch):
    """La mesure ci-dessus n'est discriminante que si le regime d'AVANT rend un resultat DIFFERENT.
    Il le rend, et c'est le no-op TOTALEMENT silencieux que le residu nommait : `resolve_unit` rend
    `None` sur un id de tuile, donc `targets = []` -- aucune emission, aucune mutation, aucune
    erreur."""
    _st, ctx, _caster, _occupant = _monde(equipe_occupant=2)
    sel = _SelBrut([TUILE_OCCUPEE])
    assert resolve_unit(sel, ctx) is None, (
        "le CONTRE-CAS est vide : `resolve_unit` resoudrait deja la tuile, donc le test ne "
        "mesurerait rien")


def test_le_collapse_laisse_INCHANGE_un_selecteur_a_domaine_UNITE(monkeypatch):
    """Non-regression : un element deja resolu (un dict) se rend lui-meme (`entity is <UnitEntity>`
    -> `return entity`). Les call-sites historiques ne bougent pas."""
    st, ctx, _caster, occupant = _monde(equipe_occupant=2)
    for valeur in (occupant, [occupant], [None, occupant]):
        sel = _SelBrut(valeur)
        assert (C._collapse_mono_cible(sel, ctx, st) or {}).get("id") == occupant["id"], valeur
        assert (resolve_unit(_SelBrut(valeur), ctx) or {}).get("id") == occupant["id"], valeur


def test_une_TUILE_VIDE_ne_frappe_rien(monkeypatch):
    """`GetUnit(entity) == null` -> le natif n'attaque pas (il n'emet que l'operation VISUELLE
    `0x25`). Le port rend `targets = []`, sans inventer de cible."""
    st, ctx, _caster, _occupant = _monde(equipe_occupant=2)
    vus = _stub_degat(monkeypatch)
    feuille = C.AttackWithAttackDamage(_SelBrut([TUILE_VIDE]), "Whatever", "Bolter", multi=False,
                                       amount=Const(100), hits=1)
    feuille.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert vus == [], vus


# --------------------------------------------------------------------------------------------
# (2) -- le jumeau `AttackWithAbilityDamage`
# --------------------------------------------------------------------------------------------
def test_le_jumeau_AttackWithAbilityDamage_resout_aussi_la_TUILE(monkeypatch):
    """`AbilityDamageBehaviour$$Execute` est l'un des TROIS `*Behaviour$$Execute` du build qui
    appellent `UnitExtensions$$GetUnit` -- meme etage, meme correctif."""
    st, ctx, _caster, occupant = _monde(equipe_occupant=2)
    vus = _stub_degat(monkeypatch)
    feuille = C.AttackWithAbilityDamage(_SelBrut([TUILE_OCCUPEE]), "Bolter", Const(100),
                                        multi=False, native_operation="ability")
    feuille.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert vus == [occupant["id"]], vus


# --------------------------------------------------------------------------------------------
# (3) et (4) -- `_select_actor` / `AreEnemies`
# --------------------------------------------------------------------------------------------
def _ancien_select_actor(node, ctx):
    """Le corps d'AVANT #889-r10, mot pour mot : le PREMIER dict de la liste evaluee. C'est le
    CONTRE-CAS -- sans lui, on ne saurait pas que la mesure discrimine."""
    from engine.dsl.base import _units_of
    for u in _units_of(node, ctx):
        if isinstance(u, dict):
            return u
    return None


def test_select_actor_rend_l_OCCUPANT_d_une_tuile():
    """`SelectActor` -> `SelectUnit(e, Any)` -> `IsTile(e) -> GetUnit(e, state)`. LU verbatim."""
    _st, ctx, _caster, occupant = _monde(equipe_occupant=2)
    sel = _SelBrut([TUILE_OCCUPEE])
    assert (T._select_actor(sel, ctx) or {}).get("id") == occupant["id"]
    assert _ancien_select_actor(_SelBrut([TUILE_OCCUPEE]), ctx) is None, (
        "le CONTRE-CAS est vide : l'ancien corps resoudrait deja la tuile")


def test_AreEnemies_sur_une_tuile_occupee_par_un_ALLIE_rend_FAUX():
    """(3) LE DISCRIMINANT. `AreEnemies` = `op_LogicalNot(AreFriendsAbilityTrigger)`, une negation
    NUE : un operande NUL y rend VRAI. Avant ce correctif, une tuile ne resolvait rien, donc
    `AreEnemies(Owner, <tuile>)` etait VRAI **pour tout occupant, allie compris** -- la degradation
    PERMISSIVE nommee par le residu. Avec la resolution d'occupant, c'est le camp de l'ALLIE qui
    est lu, et le verdict natif est FAUX."""
    _st, ctx, caster, allie = _monde(equipe_occupant=1)
    assert allie["team"] == caster["team"] == 1, "montage : l'occupant doit etre un ALLIE"
    assert AreEnemies(_SelBrut([caster]), _SelBrut([TUILE_OCCUPEE])).should_trigger(ctx) is False
    assert AreFriends(_SelBrut([caster]), _SelBrut([TUILE_OCCUPEE])).should_trigger(ctx) is True


def test_TEMOIN_sur_un_ENNEMI_les_deux_regimes_s_accordent():
    """(4) Sans ce temoin, la mesure ci-dessus pourrait n'exprimer que « la tuile resout », pas
    « c'est le CAMP de l'occupant qui est lu ». Sur un ENNEMI, ancien et nouveau regime rendent
    tous deux VRAI -- l'ecart est donc bien porte par le camp, et par lui seul."""
    _st, ctx, caster, ennemi = _monde(equipe_occupant=2)
    assert ennemi["team"] != caster["team"]
    assert AreEnemies(_SelBrut([caster]), _SelBrut([TUILE_OCCUPEE])).should_trigger(ctx) is True
    # le regime d'AVANT rendait VRAI lui aussi (operande nul -> negation nue) : meme verdict.
    assert _ancien_select_actor(_SelBrut([TUILE_OCCUPEE]), ctx) is None


def test_une_tuile_VIDE_laisse_AreEnemies_dans_le_regime_operande_NUL():
    """Une tuile sans occupant ne resout toujours rien : `SelectActor` rend `null`, `AreFriends`
    rend FAUX et `AreEnemies` -- negation NUE -- rend VRAI. C'est le regime deja porte par #963-r4,
    et ce correctif ne le touche pas."""
    _st, ctx, caster, _occ = _monde(equipe_occupant=2)
    assert T._select_actor(_SelBrut([TUILE_VIDE]), ctx) is None
    assert AreEnemies(_SelBrut([caster]), _SelBrut([TUILE_VIDE])).should_trigger(ctx) is True


def test_le_pied_SECONDAIRE_d_une_multi_hex_resout_en_son_unite():
    """`UnitExtensions$$GetUnit` sur une tuile lit son `TileContentComponent` puis BOUCLE : le
    contenu est l'entite-PIED, re-resolue en son proprietaire. N'IMPORTE QUEL pied rend l'unite --
    c'est le foyer `_occupants_by_tile`, indexe par les pieds."""
    st, ctx, _caster, occupant = _monde(equipe_occupant=2)
    occupant["feet"] = [(1, 0), (2, 0)]                      # la multi-hex couvre la tuile 502
    ctx = replace(ctx, units=list(ctx.units))
    assert (T._select_actor(_SelBrut([TUILE_VIDE]), ctx) or {}).get("id") == occupant["id"]
    assert (C._collapse_mono_cible(_SelBrut([TUILE_VIDE]), ctx, st) or {}).get("id") \
        == occupant["id"]
