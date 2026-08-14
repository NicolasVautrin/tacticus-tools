"""#1034 -- CLIQUET de l'etage `IdunBattle.Entities.UnitExtensions$$GetUnit` des behaviours de degat.

CE QUE CE FICHIER GARDE. Les trois `*Behaviour$$Execute` qui frappent une liste de cibles
re-resolvent CHAQUE entite rendue par le selecteur avant de taper. L'ensemble des trois est
**DERIVE des xrefs entrantes** de `IdunBattle.Entities.UnitExtensions$$GetUnit` (la surcharge
`IEntity`), pas enumere a la main :

    IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$Execute
    IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$Execute
    IdunBattle.Entities.Behaviours.DirectDamageBehaviour$$Execute

et le squelette y est le MEME -- `targets = <targetSel>.Select(entities)` (slot **0** d'
`ITargetsSelector`, LU dans `data/symbols/<build>/metadata/interface_slots.tsv`), puis
`unit = UnitExtensions.GetUnit(entity, state)` par entite, `null` -> la cible est SAUTEE.

⚠ CE N'EST PAS `IdunBattle.DSL.TargetsSelector$$SelectAllUnits` (slot **3**). Cette methode-la
existe et re-resout, elle aussi, mais AUCUN de ces trois behaviours ne la demande. Le test le
figerait mal en la nommant : ce qui est garde ici, c'est le `GetUnit` DU BEHAVIOUR.

⚠ ET LE CONTRAT NEGATIF COMPTE AUTANT. `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
(qui `SelectFirst` son caster, `Select` ses cibles, les trie et pousse chacune TELLE QUELLE dans
l'`AbilityEntities` de son enfant) et `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute`
(dont le seul gate par cible est `UnitExtensions$$HasFlag(entity, 6)`) sont **ABSENTS** de ces
xrefs. Greffer la resolution sur un `AddEffect` poserait sur l'UNITE un effet que le natif pose
sur la TUILE -- l'erreur symetrique de celle que ce fichier ferme.

LES CINQ ETAGES :

  [1] `_get_unit` branche par branche, contre la boucle native (unite -> elle-meme ; tuile ->
      occupant ; **pied SECONDAIRE d'une multi-hex** -> la meme unite, ce qui EST la boucle
      `tuile -> pied -> proprietaire` ; tuile vide -> None ; entite non resolvable -> None ;
      occupant MORT -> None).
  [2] Les TROIS feuilles frappent bien l'occupant quand le selecteur rend des IDS DE TUILE.
  [3] CONTRE-EPREUVE ADVERSARIALE -- on remplace `_get_unit` par l'identite (le code d'AVANT
      #1034) et on exige que [2] TOMBE. Une garde qui ne rougit pas sur la mutation qu'elle
      pretend interdire ne garde rien.
  [4] VALUE-PRESERVING -- sur un selecteur qui rend deja des DICTS d'unite (le regime de tous
      les call-sites d'avant #1034), la resolution est l'IDENTITE : memes cibles, meme ordre.
  [5] Le contrat negatif ci-dessus, execute : le module des behaviours d'EFFET n'importe pas
      `_get_unit`, et les trois sites de `combat.py` l'appellent (garde par AST, pas par prose).

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE : ce fichier construit trois feuilles de `behaviours/combat.py`, donc
#: il traverse le vocabulaire DSL, les Operations de degat et le board de pathfinding, plus la
#: cascade des quatre `conftest.py`. `**/` exige un SEGMENT, d'ou les deux globs.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "L'etage `GetUnit` des behaviours de degat et tout ce que sa fermeture d'imports "
              "traverse (feuilles de combat, vocabulaire DSL, resolution d'occupant, board). "
              "`build: False` : rien n'est fige ici qui soit LU dans le binaire -- l'ensemble "
              "des trois behaviours est derive des xrefs, il n'est pas recopie en constante.",
}

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest                                                              # noqa: E402

from engine.dsl.base import DslContext, TargetsSelector                    # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.behaviours import combat                      # noqa: E402


# --- substrat : un board REEL (le type de production, pas un double) ------------------------
#: 3x3 d'ids 1..9, colonne-ligne en lecture directe : id = col * 3 + row + 1.
_TILES = [{"id": c * 3 + r + 1, "col": c, "row": r} for c in range(3) for r in range(3)]


def _board() -> Board:
    return Board(_TILES)


def _unit(uid: int, feet, alive: bool = True) -> dict:
    """Dict d'unite au format de la face COMBAT (`behaviours/context.py::_unit_dict`) : `pos` = la
    MAIN TILE (= `feet[0]`), `feet` = l'EMPREINTE en couples `(col, row)`. `hp`/`hpMax` sont
    OBLIGATOIRES : `dsl.base._is_alive` mirrore `HealthComponent$$IsAlive`, et un dict sans sante
    y est MORT (degradation conservatrice nommee) -- donc absent de toute resolution d'occupant."""
    feet = [(int(c), int(r)) for c, r in feet]
    return {"id": uid, "alive": alive, "hp": 100, "hpMax": 100,
            "pos": {"col": feet[0][0], "row": feet[0][1]},
            "feet": list(feet)}


def _ctx(units, caster=None) -> DslContext:
    return DslContext(units=list(units), caster=caster, board=_board())


class _Selector(TargetsSelector):
    """Selecteur-double qui rend VERBATIM ce qu'on lui donne -- le role de `Select` (slot 0), dont
    le contrat natif est de rendre des ENTITES BRUTES (unites, tuiles, ...)."""

    def __init__(self, items):
        self.items = items

    def select(self, ctx):
        return list(self.items)


class _Ectx:
    """Contexte d'execution minimal : `state` + `emit`. Les feuilles n'en lisent rien d'autre une
    fois l'Operation substituee."""

    def __init__(self, state):
        self.state = state
        self.events: list = []

    def emit(self, name, **kw):
        self.events.append((name, kw))


class _State:
    """`state.get_entity` seul est traverse par les feuilles testees (il alimente le `StatsComponent`
    du caster) ; `None` rend un percage de profil nu, ce qui suffit -- on ne mesure pas le degat."""

    board = None

    def get_entity(self, _uid):
        return None


# ------------------------------------------------------------------------------------------
# [1] `_get_unit`, branche par branche
# ------------------------------------------------------------------------------------------

def test_1_unite_se_rend_elle_meme():
    """`if (entity is <UnitEntity>) return entity;` -- et c'est l'IDENTITE, pas une copie."""
    u = _unit(10, [(0, 0)])
    ctx = _ctx([u])
    assert combat._get_unit(u, ctx) is u


def test_1_tuile_rend_son_occupant():
    """`if (entity is <TileEntity>) { content.IsFilled() -> state.GetEntity(content) }`."""
    u = _unit(10, [(1, 1)])                       # (col=1,row=1) -> id 1*3+1+1 = 5
    ctx = _ctx([u])
    assert ctx.board.id_at(1, 1) == 5
    assert combat._get_unit(5, ctx) is u


def test_1_pied_secondaire_rend_la_meme_unite():
    """LA BOUCLE NATIVE : le `TileContentComponent` d'une tuile porte l'entite-PIED, que la
    surcharge PIED re-resout en son PROPRIETAIRE. N'IMPORTE QUEL pied d'une multi-hex rend donc
    SON unite -- une resolution par la seule main tile rendrait `None` sur le pied secondaire."""
    u = _unit(10, [(0, 0), (0, 1)])               # main tile id 1, pied secondaire id 2
    ctx = _ctx([u])
    assert combat._get_unit(1, ctx) is u
    assert combat._get_unit(2, ctx) is u          # <- ce que la main tile seule raterait


def test_1_tuile_vide_et_entite_non_resolvable_rendent_none():
    """`!content.IsFilled() -> return null` et la branche terminale `return null`."""
    ctx = _ctx([_unit(10, [(0, 0)])])
    assert combat._get_unit(9, ctx) is None       # (2,2) : personne
    assert combat._get_unit(None, ctx) is None
    assert combat._get_unit("nope", ctx) is None
    assert combat._get_unit(True, ctx) is None    # un bool N'EST PAS un id de tuile
    assert combat._get_unit(4242, ctx) is None    # hors board


def test_1_occupant_mort_rend_none():
    """`KillUnit` libere le `TileContentComponent` : un mort n'occupe plus sa tuile (#57m)."""
    ctx = _ctx([_unit(10, [(0, 0)], alive=False)])
    assert combat._get_unit(1, ctx) is None


def test_1_un_id_d_unite_est_REFUSE_pas_resolu():
    """LE PIEGE QUE LE NATIF NE PEUT PAS AVOIR. Cote ECS, un `Entity` est unite OU tuile, jamais
    ambigu. Cote port, les deux espaces d'ids se CHEVAUCHENT : un `UnitSet([<id d'unite>])` (arbre
    fautif, cf. la contre-epreuve #929-r3 de `test_944_combat_behaviours_offline.py`) partirait par
    la voie TUILE et resoudrait sur la tuile HOMONYME -- soit une unite silencieusement FAUSSE, soit
    `None`, donc un no-op silencieux. On LEVE, en nommant la cause."""
    u = _unit(10, [(1, 1)])

    class _StateQuiConnaitLUnite(_State):
        def get_entity(self, uid):
            return object() if uid == 5 else None    # `5` est AUSSI l'id de la tuile (1,1)

    ctx = _ctx([u])
    with pytest.raises(TypeError, match="pas une entite-tuile"):
        combat._get_unit(5, ctx, _StateQuiConnaitLUnite())
    # ... et SANS ce state, le meme `5` reste un id de tuile parfaitement legitime.
    assert combat._get_unit(5, ctx, _State()) is u


def test_1_position_col_row_est_aussi_une_tuile():
    """Le port porte la tuile sous DEUX formes (id d'entite-tuile, couple `(col,row)`) ; les deux
    designent la meme entite native, donc les deux doivent resoudre."""
    u = _unit(10, [(2, 0)])
    ctx = _ctx([u])
    assert combat._get_unit((2, 0), ctx) is u


# ------------------------------------------------------------------------------------------
# [2] les TROIS feuilles frappent l'occupant quand le selecteur rend des TUILES
# ------------------------------------------------------------------------------------------

def _cibles_ability(monkeypatch, items, mute_get_unit=False):
    """`AttackWithAbilityDamage(multi=True)` -> `AbilityDamageBehaviour$$Execute`."""
    vus: list = []
    monkeypatch.setattr(combat.AttackDamageOperation, "execute_ability_attack",
                        lambda state, src, tgt, *a, **k: vus.append(tgt) or {"total": 1})
    if mute_get_unit:
        monkeypatch.setattr(combat, "_get_unit", lambda entity, entities, state=None: entity)
    caster = _unit(1, [(0, 2)])
    cible_a = _unit(10, [(1, 1)])                 # tuile 5
    cible_b = _unit(11, [(2, 1)])                 # tuile 8
    ctx = _ctx([caster, cible_a, cible_b], caster=caster)
    leaf = combat.AttackWithAbilityDamage(_Selector(items), "attackMelee", combat_amount(),
                                          multi=True, native_operation="ability")
    leaf.execute(ctx, _Ectx(_State()))
    return vus


def combat_amount():
    class _A:
        def evaluate(self, _ctx):
            return 100
    return _A()


def test_2_ability_damage_frappe_les_occupants(monkeypatch):
    assert _cibles_ability(monkeypatch, [5, 8]) == [10, 11]


def test_2_ability_damage_saute_la_tuile_vide(monkeypatch):
    """`GetUnit(entity) == null` -> le natif n'emet que l'operation `0x25` et CONTINUE."""
    assert _cibles_ability(monkeypatch, [5, 9, 8]) == [10, 11]


def _cibles_attack(monkeypatch, items, mute_get_unit=False):
    """`AttackWithAttackDamage(multi=True)` -> `AttackDamageBehaviour$$Execute`."""
    vus: list = []
    monkeypatch.setattr(combat.AttackDamageOperation, "execute_normal_like",
                        lambda state, src, tgt, *a, **k: vus.append(tgt) or {"total": 1})
    if mute_get_unit:
        monkeypatch.setattr(combat, "_get_unit", lambda entity, entities, state=None: entity)
    caster = _unit(1, [(0, 2)])
    ctx = _ctx([caster, _unit(10, [(1, 1)]), _unit(11, [(2, 1)])], caster=caster)
    leaf = combat.AttackWithAttackDamage(_Selector(items), "someAbility", "attackMelee",
                                         multi=True, amount=combat_amount())
    leaf.execute(ctx, _Ectx(_State()))
    return vus


def test_2_attack_damage_frappe_les_occupants(monkeypatch):
    assert sorted(_cibles_attack(monkeypatch, [5, 8])) == [10, 11]


def _cibles_direct(monkeypatch, items, mute_get_unit=False):
    """`DirectDamage` -> `DirectDamageBehaviour$$Execute`."""
    vus: list = []
    monkeypatch.setattr(combat.AttackDamageOperation, "execute_direct",
                        lambda state, src, tgt, *a, **k: vus.append(tgt) or {"total": 1})
    if mute_get_unit:
        monkeypatch.setattr(combat, "_get_unit", lambda entity, entities, state=None: entity)
    caster = _unit(1, [(0, 2)])
    ctx = _ctx([caster, _unit(10, [(1, 1)]), _unit(11, [(2, 1)])], caster=caster)
    leaf = combat.DirectDamage(_Selector(items), combat_amount())
    leaf.execute(ctx, _Ectx(_State()))
    return vus


def test_2_direct_damage_frappe_les_occupants(monkeypatch):
    assert sorted(_cibles_direct(monkeypatch, [5, 8])) == [10, 11]


# ------------------------------------------------------------------------------------------
# [3] CONTRE-EPREUVE : la mutation « pas de resolution » doit faire TOMBER [2]
# ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fabrique", [_cibles_ability, _cibles_attack, _cibles_direct])
def test_3_sans_resolution_la_feuille_ne_frappe_pas_l_occupant(monkeypatch, fabrique):
    """MUTATION ADVERSARIALE -- on remet le comportement d'AVANT #1034 (l'entite est prise telle
    quelle) et on exige que la feuille CESSE de frapper les occupants : soit elle leve (les deux
    familles d'attaque faisaient `(u or {}).get("id")` sur un `int` -> `AttributeError`), soit
    elle rend une liste vide (la famille DIRECT jetait l'element en silence). Les deux sont des
    echecs ; ce qui est INTERDIT, c'est de rendre `[10, 11]` sans resolution."""
    try:
        vus = fabrique(monkeypatch, [5, 8], mute_get_unit=True)
    except AttributeError:
        return                                    # la forme « crash » -- c'est le symptome mesure
    assert sorted(vus) != [10, 11], "la mutation ne change RIEN : la garde ne garde pas"


# ------------------------------------------------------------------------------------------
# [4] VALUE-PRESERVING sur le regime d'avant : des DICTS d'unite
# ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fabrique,attendu", [(_cibles_ability, [10, 11]),
                                              (_cibles_attack, [10, 11]),
                                              (_cibles_direct, [10, 11])])
def test_4_selecteur_unit_domain_inchange(monkeypatch, fabrique, attendu):
    """Tous les call-sites d'avant #1034 passent des dicts d'unite. Sur eux, `GetUnit` est
    l'IDENTITE (branche `is <UnitEntity>`), donc le resultat doit etre STRICTEMENT le meme --
    c'est ce qui rend l'etage sur, et c'est verifie, pas suppose."""
    items = [_unit(10, [(1, 1)]), _unit(11, [(2, 1)])]
    assert sorted(fabrique(monkeypatch, items)) == attendu


def test_4_identite_sur_les_dicts(monkeypatch):
    """Meme propriete, prise a la racine : la resolution ne REMPLACE jamais un dict d'unite par un
    autre objet -- pas meme par l'occupant de sa propre tuile (qui pourrait etre un homonyme)."""
    a = _unit(10, [(1, 1)])
    b = dict(a)                                   # meme position, autre objet
    ctx = _ctx([b])
    assert combat._get_unit(a, ctx) is a          # `a`, pas `b`


# ------------------------------------------------------------------------------------------
# [5] le contrat, par AST -- pas par prose
# ------------------------------------------------------------------------------------------

_COMBAT = Path(__file__).resolve().parents[3] / "engine/runner/abilities/behaviours/combat.py"


def _appels_get_unit(fn: ast.FunctionDef) -> int:
    return sum(1 for n in ast.walk(fn)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_get_unit")


def test_5_les_trois_feuilles_appellent_get_unit():
    """Retirer l'appel ne casse AUCUN import et ne leve rien tant qu'aucun selecteur tuile n'est
    joue -- exactement la regression silencieuse que #1034 ferme. On la garde donc structurellement,
    classe par classe."""
    arbre = ast.parse(_COMBAT.read_text(encoding="utf-8"))
    par_classe = {n.name: n for n in ast.walk(arbre) if isinstance(n, ast.ClassDef)}
    for nom in ("AttackWithAbilityDamage", "AttackWithAttackDamage", "DirectDamage"):
        cls = par_classe.get(nom)
        assert cls is not None, "classe " + nom + " introuvable"
        exe = next((f for f in cls.body
                    if isinstance(f, ast.FunctionDef) and f.name == "execute"), None)
        assert exe is not None, nom + ".execute introuvable"
        assert _appels_get_unit(exe) >= 1, nom + ".execute n'appelle plus _get_unit"


def test_5_les_behaviours_d_effet_ne_resolvent_pas():
    """CONTRAT NEGATIF, execute. `AddEffectBehaviour$$Execute` est ABSENT des xrefs entrantes de
    `IdunBattle.Entities.UnitExtensions$$GetUnit` : il pose l'effet sur l'entite BRUTE. Si un jour
    quelqu'un « harmonise » les feuilles d'effet sur celles de degat, ce test le dit."""
    effets = _COMBAT.parent / "effects.py"
    if not effets.exists():                       # le module a change de nom : le dire, pas passer
        pytest.skip("behaviours/effects.py absent -- contrat negatif a re-ancrer")
    assert "_get_unit" not in effets.read_text(encoding="utf-8"), (
        "un behaviour d'EFFET re-resout l'entite : le natif, lui, pose sur la TUILE")
