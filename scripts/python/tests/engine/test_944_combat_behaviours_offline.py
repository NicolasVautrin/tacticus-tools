"""#944 -- gardes OFFLINE des trois residus du foyer `abilities/behaviours/combat.py`
(`#929-r3`, `#889-r5-r1`, `#889-r5-r2`) et du quatrieme qui le traverse (`#925-r2`).

Ce que chaque etage FIGE, et **pourquoi rien d'autre ne le tenait** :

1. **`hateful_assault_tree()` s'EXECUTE.** Le chemin LEVAIT en production
   (`AttributeError: 'int' object has no attribute 'get'`) et ses **10** tests etaient VERTS parce
   qu'AUCUN n'appelait `execute_behaviour` -- les 4 `test_live_*` mesurent le natif, les 6
   `test_port_*` n'appellent que `matches`. Le discriminant n'est donc pas une VALEUR, c'est le
   fait d'EXECUTER la feuille : cet etage la joue pour de vrai, avec un `state.rng` cale, et exige
   que l'attaque parte SUR LE MOVER. La contre-epreuve rejoue le patron fautif (`UnitSet` d'ids) et
   exige qu'il LEVE encore -- sans elle, l'etage passerait meme si la cause avait ete masquee
   ailleurs.

2. **Le sens d'ITERATION de `UseActiveAbility`.** Le natif boucle sur les CASTERS (`+0x58`,
   slot 0 `Select`) et prend UNE cible (`+0x60`, slot 1 `SelectFirst`) ; le port faisait l'inverse.
   La divergence est INERTE sur les 14 call-sites portes (tous mono-cible), donc **aucun test
   existant ne pouvait la voir** : il faut un montage a 2 casters x 2 cibles pour la rendre
   observable, et c'est exactement ce que fait cet etage. Il figera aussi l'ABSENCE de tri (le
   natif n'appelle pas `OrderBy` ici) et l'ordre d'evaluation (cible AVANT la boucle).

3. **L'ordinal ECRIT au site pour `InvalidTargetPolicy`.** Deux crans distincts, et le second est
   celui qu'on oublie : `probe_313` compare le MIRROR au BUILD (il redeviendrait vert apres un
   renumerotage suivi d'une regeneration du mirror), tandis que cet etage garde la valeur
   **mesuree a la conversion** -- `Skip = 2`, le litteral LU dans
   `DSLBehaviors$$UseNormalAttackIfAble`. Il verifie aussi que l'ordinal nu `2` designe autre chose
   dans les enums voisins, ce qui est la raison d'etre du nom.

4. **`is_outside_attack` pilote l'`On(PreAttack = 5)` sur la voie `amount`.** Ce vecteur ne
   l'exprimait pas, donc il n'emettait **JAMAIS** l'event -- le residu l'avait ecrit a l'envers
   (il annoncait N emissions, il y en avait 0). L'etage mesure les DEUX regimes du drapeau, et la
   forme HAZE (N feuilles nues sous UN englobant) qui est le seul cas ou le compte natif n'est pas
   celui des feuilles.

Tests OFFLINE (aucun runner) -- ils tournent en quelques dixiemes de seconde.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le foyer PARTAGE de la tranche : les trois classes `Use*` fusionnees sur la boucle
        # native, et le threading d'`is_outside_attack` du mode `amount`.
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        # L'Operation qui porte desormais le gate d'`On(PreAttack = 5)` sur la voie `amount`.
        "scripts/python/engine/runner/operations/damage_ops/normal_like.py",
        # Le porteur du bug DORMANT (#929-r3) et l'arbre repare.
        "scripts/python/engine/runner/operations/triggers/loki/hateful_assault.py",
        # Le seul call-site `amount` a feuilles NUES : il emet l'`On(5)` de son englobant.
        "scripts/python/engine/runner/operations/triggers/loki/haze_of_corruption.py",
        # Le mirror d'enum NEUF et le registre qui le tient en bijection.
        "scripts/python/engine/entities/invalid_target_policy.py",
        "scripts/python/probe_313_enum_mirror_bijection.py",
        # Le seul lecteur du champ diagnostique renomme (`if_able` -> `invalid_target_policy`).
        "scripts/python/engine/runner/abilities/darkangels.py",
        # Le vecteur d'emission dont ces gardes comptent les appels.
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # Tires par l'import de `probe_313_enum_mirror_bijection` (etage 3 lui emprunte
        # `current_build`, `enum_natif` et `REGISTRE` au lieu de re-transcrire une seconde
        # table -- une transcription locale pourrait diverger de celle du cliquet).
        "scripts/python/repo_read.py",
        "scripts/python/verdict_cache.py",
        # LU par la cascade d'import d'`engine` (`_monde` construit un `State`) -- confronte par
        # l'empreinte #486-r15, pas devine.
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "L'etage 3 assertionne des ORDINAUX (`InvalidTargetPolicy` 1/2/3) LUS dans "
        "`data/symbols/<CURRENT>/frida/enums.tsv` du hash courant, et la DISJONCTION de l'ordinal "
        "`2` avec ses voisins d'enum. Un renumerotage au changement de build les rend faux sans "
        "qu'une ligne du depot bouge -- c'est precisement ce que ce fichier doit voir. Les etages "
        "1, 2 et 4 sont build-independants (ils portent sur des structures de port), mais le "
        "fichier est indivisible."
    ),
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.dsl.effects import ExecutionContext                             # noqa: E402
from engine.entities.effects_state import EffectsState                      # noqa: E402
from engine.entities.invalid_target_policy import InvalidTargetPolicy       # noqa: E402
from engine.entities.selectors.accessors import Target                      # noqa: E402
from engine.entities.selectors.units import UnitSet                         # noqa: E402
from engine.entities.stats import StatType, UnitStats                       # noqa: E402
from engine.entities.unit_context import UnitContext                        # noqa: E402
from engine.runner.abilities.behaviours.combat import (                     # noqa: E402
    AttackWithAttackDamage, UseActiveAbility, UseNormalAttack, UseNormalAttackIfAble)
from engine.runner.abilities.behaviours.context import entities_from_state  # noqa: E402
from engine.runner.components import (                                      # noqa: E402
    HealthComponent, OwnerComponent, PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.damage import AttackDamageOperation           # noqa: E402
from engine.runner.operations.triggers.loki.hateful_assault import (        # noqa: E402
    hateful_assault_tree)
from engine.runner.prng import IntBasedMersenneTwister                      # noqa: E402
from engine.runner.state import State                                       # noqa: E402

import probe_313_enum_mirror_bijection as P313                              # noqa: E402


#: Seed arbitraire mais FIGE : les etages qui tirent (1 et 4) doivent etre reproductibles.
SEED = 4242


def _monde(specs):
    """`State` synthetique. `specs` = [(visual_id, col, row, team)]. PV volontairement enormes :
    aucun etage de ce fichier ne mesure une mort, et une cible qui tombe changerait le nombre de
    coups appliques."""
    state = State()
    state.effects = EffectsState.seed({})
    ids = {}
    for vid, col, row, team in specs:
        e = state.add_entity()
        e.add_component(UnitComponent(visual_id=vid, alive=True))
        e.add_component(OwnerComponent(team=team, player=(3 if team == 1 else 4)))
        e.add_component(PositionComponent(col=col, row=row))
        e.add_component(HealthComponent(hp=1000000, hp_max=1000000))
        stats = UnitStats()
        stats.ensure_seeded(StatType.FIXED_ARMOR, 0)
        e.add_component(StatsComponent(ctx=UnitContext(
            entity_id=e.id, visual_id=vid, active_ability_level=50,
            passive_ability_level=50, ability_variables_multiplier=100, stats=stats)))
        ids[vid] = e.id
    state.rng = IntBasedMersenneTwister(SEED)
    return state, ids


def _unit_dict(state, uid):
    """Le dict d'unite tel qu'un selecteur natif le rend (une `LiveUnit` de l'`AbilityEntities`)."""
    for u in entities_from_state(state, uid).units:
        if u.get("id") == uid:
            return u
    raise AssertionError("unite %r absente de l'AbilityEntities" % (uid,))


# ------------------------------------------------------------------ 1. #929-r3 : le bug DORMANT

def test_929r3_l_arbre_hateful_assault_s_execute_et_frappe_le_mover():
    """`hateful_assault_tree().execute(...)` LEVAIT (`AttributeError`) sur `master`. Il doit
    desormais s'executer ET porter l'attaque sur le MOVER, pas ailleurs.

    Le montage est celui du vecteur natif : `EvaluatePreMoveTriggers` construit son
    `AbilityEntities` avec `caster = actor = target = l'unite qui bouge`, sauf que le behaviour de
    `HatefulAssault` est evalue avec `caster = Owner` (Angrax) et `target = Target@+0x60` (le
    mover) -- ce que reproduit `entities_from_state(state, owner, mover, mover)`."""
    state, ids = _monde([("blackTerminator", 2, 2, 1), ("necroWarden", 2, 3, 2)])
    owner, mover = ids["blackTerminator"], ids["necroWarden"]
    ectx = ExecutionContext(state=state, rng=state.rng)
    hateful_assault_tree().execute(entities_from_state(state, owner, mover, mover), ectx)

    emis = [n for n, _ in ectx.emitted]
    assert emis == ["AttackWithAttackDamage", "AddEffect"], (
        "les DEUX feuilles de `HatefulAssaultAbility$$CreateBehaviour` doivent s'executer, "
        "dans l'ordre du `op_BitwiseAnd` natif ; obtenu %r" % (emis,))

    atk = dict(ectx.emitted[0][1])
    assert atk["caster"] == owner, "l'attaquant est `Owner@+0x30` (Angrax)"
    assert atk["target"] == mover, "la cible est `Target@+0x60` (le mover)"
    # La MAGNITUDE n'est pas l'objet de cet etage (elle est confrontee au natif dans
    # `test_hateful_assault_live.py`) : ce qui est FIGE ici, c'est qu'un coup a REELLEMENT ete
    # applique -- un `total` nul signerait un no-op silencieux, l'autre visage du meme bug.
    assert (atk["total"] or 0) > 0, (
        "l'attaque doit appliquer un degat reel ; `total=%r` signale un no-op" % (atk["total"],))

    mark = dict(ectx.emitted[1][1])
    assert mark["effect_type"] == 1175 and mark["target"] == mover and mark["placed"], (
        "le marqueur 1175 `HatefulAssault_AlreadyAttacked` doit etre pose sur le mover")


def test_929r3_le_patron_fautif_leve_toujours_contre_epreuve():
    """CONTRE-EPREUVE : le patron d'origine -- `UnitSet` d'**ids** passe a une feuille `multi` --
    doit LEVER encore. Sans elle, l'etage precedent resterait vert meme si la cause avait ete
    masquee (par un `try/except`, ou par un filtre defensif ajoute dans la feuille), et on aurait
    un garde qui ne garde rien.

    ⚠ Ce que cette contre-epreuve dit AUSSI : la reparation n'a **pas** consiste a rendre
    `AttackWithAttackDamage` tolerante aux entiers. Le natif passe un SELECTEUR
    (`Target@DSLSelectors+0x60`), donc c'est l'ARBRE qui etait faux, pas la feuille.

    ⚠ #1034 A CHANGE LE *TYPE* DE L'EXCEPTION, PAS LA PROPRIETE GARDEE. La feuille porte desormais
    l'etage `IdunBattle.Entities.UnitExtensions$$GetUnit` du behaviour natif, donc elle RESOUT bien
    un element a domaine TUILE (id de tuile / `(col,row)`) en son occupant. Un id d'**unite**, lui,
    reste un arbre fautif -- et il est desormais REFUSE EXPLICITEMENT (`TypeError` nommee) au lieu
    de produire l'`AttributeError` opaque d'avant. Le durcissement est reel : sans ce refus, l'id
    d'unite serait parti par la voie TUILE (les deux espaces d'ids se CHEVAUCHENT cote port) et
    aurait rendu soit l'occupant d'une tuile HOMONYME -- silencieusement faux -- soit `None`, donc
    un no-op silencieux, ce que cette contre-epreuve existe precisement pour interdire."""
    state, ids = _monde([("blackTerminator", 2, 2, 1), ("necroWarden", 2, 3, 2)])
    owner, mover = ids["blackTerminator"], ids["necroWarden"]
    ectx = ExecutionContext(state=state, rng=state.rng)
    feuille = AttackWithAttackDamage(UnitSet([mover]), "HatefulAssault", "Power",
                                     is_melee=True, multi=True, level_slot="passive")
    with pytest.raises(TypeError, match="pas une entite-tuile"):
        feuille.execute(entities_from_state(state, owner, mover, mover), ectx)


def test_929r3_l_arbre_ne_prend_plus_d_id():
    """`HatefulAssaultAbility$$CreateBehaviour` ne recoit AUCUN id : ses deux feuilles lisent
    `Target@+0x60` dans l'`AbilityEntities`. L'arbre porte doit avoir la meme forme -- un
    parametre d'id ré-ouvrirait la porte par laquelle le bug est entre."""
    import inspect
    assert list(inspect.signature(hateful_assault_tree).parameters) == [], (
        "l'arbre ne doit prendre aucun parametre (le natif n'en prend pas)")


# --------------------------------------------- 2. #889-r5-r1 : la boucle porte sur les CASTERS

class _AttaquesCaptees:
    """Substitut d'`AttackDamageOperation.execute` : enregistre les couples (caster, cible) SANS
    toucher a l'etat. C'est l'ETAGE qu'on mesure -- la boucle du behaviour -- et non le degat, qui
    a ses propres gardes."""

    def __init__(self):
        self.appels = []

    def __call__(self, state, caster_id, target_id, *a, **kw):
        self.appels.append((caster_id, target_id))
        return {"total": 1, "target": target_id, "ranged": False, "profile": None,
                "did_crit": False, "did_block": False, "finish_attack": []}


@pytest.mark.parametrize("cls", [UseActiveAbility, UseNormalAttack, UseNormalAttackIfAble])
def test_889r5r1_la_boucle_porte_sur_les_casters_et_la_cible_est_selectfirst(monkeypatch, cls):
    """`UseActiveAbilityBehaviour$$Execute`, lu aux slots d'interface :

        targets = (+0x60 target).SelectFirst(entities)      // ITargetsSelector, 2e slot
        foreach (caster in (+0x58 caster).Select(entities)) // ITargetsSelector, 1er slot
            processor.ActiveAbility(caster, targets, abilityType, options)

    (#943 -- les deux numeros de slot d'`ITargetsSelector` ne sont plus ECRITS en fin de ces deux
    lignes : la ligne SUIVANTE porte un `processor.<Nom>`, et `probe_477r24r1` juge le recepteur sur
    le SPAN du couple -- il appariait donc `(slot 0, ActiveAbility)`, alors que le slot 0 cite ici
    est celui d'une AUTRE interface. Ils restent lisibles au foyer,
    `runner/abilities/behaviours/combat.py::UseActiveAbility`.)

    Montage DISCRIMINANT (2 casters x 2 cibles) : le natif produit **2** dispatches, tous deux sur
    la PREMIERE cible. Le port d'avant produisait **2** dispatches aussi, mais sur les DEUX cibles
    et depuis le PREMIER caster -- meme cardinal, couples opposes. C'est pourquoi le test compare
    les COUPLES et pas un compte.

    Les trois classes sont exercees : le second volet de #889-r5-r1 etait qu'elles partagent un
    seul corps, et un `parametrize` qui passerait sur deux mais pas la troisieme le dirait."""
    state, ids = _monde([("c1", 1, 1, 1), ("c2", 1, 2, 1), ("t1", 3, 1, 2), ("t2", 3, 2, 2)])
    cap = _AttaquesCaptees()
    monkeypatch.setattr(AttackDamageOperation, "execute", staticmethod(cap))

    c1, c2 = ids["c1"], ids["c2"]
    t1, t2 = ids["t1"], ids["t2"]
    casters = UnitSet([_unit_dict(state, c1), _unit_dict(state, c2)])
    cibles = UnitSet([_unit_dict(state, t1), _unit_dict(state, t2)])

    ectx = ExecutionContext(state=state, rng=state.rng)
    cls(casters, cibles).execute(entities_from_state(state, c1, t1), ectx)

    assert cap.appels == [(c1, t1), (c2, t1)], (
        "attendu : UN dispatch par CASTER, tous sur la PREMIERE cible (`SelectFirst`). "
        "L'ancien port rendait [(%d, %d), (%d, %d)] -- il iterait les CIBLES. Obtenu : %r"
        % (c1, t1, c1, t2, cap.appels))


def test_889r5r1_l_ordre_des_casters_est_celui_du_selecteur_aucun_tri(monkeypatch):
    """`$$Execute` n'appelle **pas** `OrderBy` sur ses casters (contraste
    `AttackBehaviour$$Execute`, qui trie quand `Count > 1`). Le port d'avant triait les CIBLES par
    id ; s'il avait transpose ce tri sur les casters, cet etage le verrait."""
    state, ids = _monde([("c1", 1, 1, 1), ("c2", 1, 2, 1), ("t1", 3, 1, 2)])
    cap = _AttaquesCaptees()
    monkeypatch.setattr(AttackDamageOperation, "execute", staticmethod(cap))

    c1, c2, t1 = ids["c1"], ids["c2"], ids["t1"]
    # Selecteur volontairement en ordre DECROISSANT d'id : un tri le remettrait a l'endroit.
    casters = UnitSet([_unit_dict(state, c2), _unit_dict(state, c1)])
    ectx = ExecutionContext(state=state, rng=state.rng)
    UseActiveAbility(casters, Target()).execute(entities_from_state(state, c1, t1), ectx)

    assert cap.appels == [(c2, t1), (c1, t1)], (
        "l'ordre des casters doit etre celui du SELECTEUR, pas l'ordre des ids ; obtenu %r"
        % (cap.appels,))


def test_889r5r1_les_trois_classes_partagent_un_seul_corps():
    """Le second volet du residu, litteralement : `UseNormalAttack` et `UseNormalAttackIfAble` ne
    doivent PAS redefinir `execute` -- sinon la reparation de la boucle ne vaudrait que pour l'une
    d'elles, ce qui est exactement l'etat d'ou l'on vient."""
    assert UseNormalAttack.__mro__[1] is UseActiveAbility
    assert UseNormalAttackIfAble.__mro__[1] is UseNormalAttack
    for cls in (UseNormalAttack, UseNormalAttackIfAble):
        assert "execute" not in vars(cls), (
            "%s redefinit `execute` : les trois noeuds sont le MEME `UseActiveAbilityBehaviour` "
            "natif et doivent partager un corps" % (cls.__name__,))


# ------------------------------------- 3. #889-r5-r2 : le champ `+0x00` porte un NOM, et lequel

def test_889r5r2_les_ordinaux_du_mirror_sont_ceux_du_build():
    """`IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy`, LU dans
    `data/symbols/<CURRENT>/frida/enums.tsv`. Le namespace est `IdunBattle.Operations` -- pas
    `IdunBattle.Entities.Enum`, ou le nom court aurait cherche en vain."""
    build = P313.current_build()
    jeu = P313.enum_natif(build, "IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy")
    assert jeu, ("l'enum natif doit exister dans le build %s -- un ensemble VIDE ferait passer "
                 "cet etage pour vert sans rien verifier" % (build,))
    port = {int(m): {m.name} for m in InvalidTargetPolicy}
    assert port == jeu, "mirror != build (%s) : port=%r jeu=%r" % (build, port, jeu)


def test_889r5r2_l_ordinal_ecrit_au_site_est_fige():
    """LE CRAN QUE `probe_313` NE TIENT PAS. Ce cliquet-la compare le MIRROR au BUILD : il
    redeviendrait VERT si un renumerotage etait suivi d'une regeneration du mirror, alors que la
    valeur ECRITE au site, elle, aurait change de sens. Cet etage garde l'ordinal **mesure a la
    conversion** -- le litteral `2` que `DSLBehaviors$$UseNormalAttackIfAble` passe a
    `System.Nullable<InvalidTargetPolicy>..ctor` juste avant le ctor du behaviour."""
    assert int(InvalidTargetPolicy.Allow) == 1
    assert int(InvalidTargetPolicy.Skip) == 2
    assert int(InvalidTargetPolicy.Error) == 3
    assert UseNormalAttackIfAble.INVALID_TARGET_POLICY == int(InvalidTargetPolicy.Skip)


def test_889r5r2_seul_ifable_ecrit_le_champ_les_deux_autres_laissent_le_nullable_vide():
    """`$$UseNormalAttack` et `$$UseActiveAbility` recopient `options` TEL QUEL sans toucher au
    champ `+0x00` : le `Nullable` reste vide, et `ActiveAbilityOperation$$ExecuteInternal` en prend
    le `GetValueOrDefault`, qui vaut `Error`. `None` cote port EST ce `Nullable` vide -- le
    rabattre sur `Error` serait une valeur INVENTEE au site."""
    assert UseActiveAbility.INVALID_TARGET_POLICY is None
    assert UseNormalAttack.INVALID_TARGET_POLICY is None


def test_889r5r2_l_ordinal_nu_designe_autre_chose_ailleurs():
    """LA RAISON D'ETRE DU NOM. `2` est un ordinal parfaitement valide dans les enums voisins de
    la MEME chaine d'appel, ou il nomme autre chose -- ecrire `2` au site n'aurait leve nulle part.
    L'etage assertionne son propre NON-VIDE : un ensemble vide de temoins passerait pour vert."""
    build = P313.current_build()
    voisins = {
        # Le champ `+0x08` des MEMES options, 7e argument d'`$$IsInvalidTarget`.
        "IdunBattle.Operations.ActiveAbilityOperation.ExecutionType": "ContinueAbility",
        # Le `selectionType` que les factories d'attaque passent a cote, dans les memes arbres.
        "IdunBattle.Entities.Enum.UnitSelectionType": None,
    }
    temoins = []
    for cle, attendu in voisins.items():
        jeu = P313.enum_natif(build, cle)
        assert jeu, "enum voisin %s introuvable dans le build %s" % (cle, build)
        noms = jeu.get(int(InvalidTargetPolicy.Skip))
        assert noms, "l'ordinal 2 doit exister dans %s (sinon il ne temoigne de rien)" % (cle,)
        assert noms != {InvalidTargetPolicy.Skip.name}, (
            "%s[2] vaut %r : il ne discrimine pas de `InvalidTargetPolicy.Skip`" % (cle, noms))
        if attendu is not None:
            assert attendu in noms, "%s[2] attendu %r, obtenu %r" % (cle, attendu, noms)
        temoins.append(cle)
    assert len(temoins) == 2, "les DEUX temoins doivent avoir ete evalues, obtenu %r" % (temoins,)


def test_889r5r2_le_mirror_est_au_registre_de_probe_313():
    """Un mirror NEUF hors registre est INVISIBLE de la bijection -- c'est par ce trou que quatre
    mirrors sont deja passes (`PathfinderType`, `KillUnitStep`, `DamageReason`, `Edge`). Il entre
    DANS LE MEME COMMIT, apparie par son nom PLEIN."""
    inscrits = {m.cls: m for m in P313.REGISTRE}
    assert "InvalidTargetPolicy" in inscrits, "mirror absent du registre de `probe_313`"
    m = inscrits["InvalidTargetPolicy"]
    assert m.cle == "IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy"
    assert m.rel == "engine/entities/invalid_target_policy.py"


# ------------------------- 4. #925-r2 : `is_outside_attack` pilote `On(5)` sur la voie `amount`

class _EventsCaptes:
    """Substitut de `pre_attack_triggers` : compte les emissions d'`On(PreAttack = 5)`."""

    def __init__(self):
        self.appels = []

    def __call__(self, state, attacker_id, target_id, **kw):
        self.appels.append((attacker_id, target_id, kw.get("ability_type")))
        return []


def _capter_on5(monkeypatch):
    """Les DEUX sites d'emission importent `pre_attack_triggers` en DIFFERE, dans le corps de la
    fonction (forme C) : substituer l'attribut du module cible MORD donc a chaque appel."""
    cap = _EventsCaptes()
    monkeypatch.setattr(
        "engine.runner.operations.triggers.dispatch.attack.pre_attack_triggers", cap)
    return cap


@pytest.mark.parametrize("outside,attendu", [(True, 1), (False, 0)])
def test_925r2_la_voie_amount_emet_on5_sous_le_gate(monkeypatch, outside, attendu):
    """La voie `amount` route par `execute_normal_like`, qui n'exprimait PAS `isOutsideAttack` et
    n'emettait donc JAMAIS `On(5)` -- alors que trois de ses quatre call-sites portent une feuille
    EMBALLEE (`DSLBehaviors$$AttackWithAttackDamage` construit `AttackDamageBehaviour` **puis**
    `AttackBehaviour` et retourne ce dernier ; `AttackBehaviour$$Execute` pousse `StartAttack`).

    ⚠ Le residu #925-r2 predisait l'INVERSE (« emet inconditionnellement », donc N pour Haze) : il
    confondait `pre_attack_hit_triggers` (`On(6)`, per-coup, bien present) avec `pre_attack_triggers`
    (`On(5)`, per-cible, absent). Le regime `False` de ce parametrize est le seul qui aurait ete
    vert sous l'ancien code -- c'est le regime `True` qui mord."""
    from engine.dsl.base import Const
    state, ids = _monde([("c1", 1, 1, 1), ("t1", 2, 1, 2)])
    cap = _capter_on5(monkeypatch)
    c1, t1 = ids["c1"], ids["t1"]
    ectx = ExecutionContext(state=state, rng=state.rng)
    AttackWithAttackDamage(Target(), "Psyker", "Psychic", is_melee=False,
                           amount=Const(500), hits=1,
                           is_outside_attack=outside).execute(
        entities_from_state(state, c1, t1), ectx)

    assert len(cap.appels) == attendu, (
        "is_outside_attack=%r -> %d emission(s) d'`On(PreAttack = 5)` attendue(s), obtenu %r"
        % (outside, attendu, cap.appels))
    if attendu:
        assert cap.appels[0][:2] == (c1, t1)


def test_925r2_la_voie_bornes_reste_gatee_de_la_meme_facon(monkeypatch):
    """NON-REGRESSION du jumeau : le gate de la voie BORNES (`execute_ability_attack`, #512-r2)
    doit rester exactement ce qu'il etait. Un fix qui aurait deplace le gate au lieu de l'ajouter
    se verrait ici."""
    state, ids = _monde([("c1", 1, 1, 1), ("t1", 2, 1, 2)])
    cap = _capter_on5(monkeypatch)
    c1, t1 = ids["c1"], ids["t1"]
    for outside, attendu in ((True, 1), (False, 0)):
        cap.appels.clear()
        ectx = ExecutionContext(state=state, rng=state.rng)
        AttackWithAttackDamage(Target(), "HatefulAssault", "Power", is_melee=True,
                               level_slot="passive",
                               is_outside_attack=outside).execute(
            entities_from_state(state, c1, t1), ectx)
        assert len(cap.appels) == attendu, (
            "voie BORNES, is_outside_attack=%r -> %d attendue(s), obtenu %r"
            % (outside, attendu, cap.appels))


def test_925r2_haze_pose_des_feuilles_nues_et_emet_un_seul_on5(monkeypatch):
    """LA FORME QUI FAIT EXCEPTION. `HazeOfCorruption_DamageTransferEffect$$
    CreateTargetTriggerBehaviour` accumule **N** feuilles `DSLBehaviors$$AttackDamage` **NUES** par
    `op_Addition` dans **UN SEUL** `DSLBehaviors$$Attack(bonded, Owner@0x148, beh)` : le natif emet
    donc **1** `On(5)`, porte par l'englobant, et **0** par feuille.

    Ce test joue le call-site REEL (`execute_behaviour`), avec deux `LeftOverDamage` substitues :
    un compte de 1 avec 2 transferts est la seule mesure qui separe << l'englobant emet >> de
    << chaque feuille emet >>."""
    from engine.runner.operations.triggers.loki import haze_of_corruption as H

    state, ids = _monde([("bonded", 1, 1, 1), ("relais", 2, 1, 1), ("mort", 3, 1, 2)])
    cap = _capter_on5(monkeypatch)
    bonded, relais, mort = ids["bonded"], ids["relais"], ids["mort"]

    trans = H.HazeOfCorruptionDamageTransferTrigger(relais)
    monkeypatch.setattr(trans, "_instance", lambda st: object())
    monkeypatch.setattr(trans, "_bonded_id", lambda st, inst, ev: bonded)
    monkeypatch.setattr(H, "left_over_damages",
                        lambda st, dying: [{"amount": 100, "profile": "Toxic"},
                                           {"amount": 200, "profile": "Toxic"}])
    # Le `RemoveEffect` du bond ET les feuilles d'attaque sont laisses REELS : seul le compte
    # d'`On(5)` est mesure, et c'est lui qui distingue les deux formes.
    feuilles = []
    vraie = AttackWithAttackDamage.execute

    def _tracer(self, entities, ectx):
        feuilles.append(bool(self.is_outside_attack))
        return vraie(self, entities, ectx)

    monkeypatch.setattr(AttackWithAttackDamage, "execute", _tracer)

    ev = H.TriggerEvent(int(H.EventTriggerType.UnitDeath), mort, mort,
                        ranged=False, profile=None, killer_id=mort, dying_id=mort)
    trans.execute_behaviour(state, ev)

    assert feuilles == [False, False], (
        "chaque feuille de transfert est un `$$AttackDamage` NU -> `is_outside_attack=False` ; "
        "obtenu %r" % (feuilles,))
    assert len(cap.appels) == 1, (
        "UN SEUL `On(PreAttack = 5)`, celui de l'englobant `$$Attack` -- N feuilles nues n'en "
        "emettent aucun ; obtenu %r" % (cap.appels,))
    assert cap.appels[0][0] == bonded, "l'attaquant du `$$Attack` englobant est le BONDE"
    assert cap.appels[0][1] == relais, "sa cible est le RELAIS (`Owner@0x148`)"
    assert cap.appels[0][2] is None, (
        "le 5e argument du `$$Attack` natif est un `AbilityOrEffect` MIS A ZERO "
        "(`local_3b8 = uStack_3b0 = local_3a8 = 0`) -- recopier `0x435` inventerait une valeur")
