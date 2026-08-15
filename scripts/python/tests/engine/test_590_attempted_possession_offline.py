"""#590 -- `1101 AttemptedPossession` : ce que le port DOIT tenir, sans monter de runner.

Ce fichier garde les SEPT points ou une lecture distraite du decompile produirait un port qui
ne rougit nulle part ailleurs. Chacun est un piege REEL, rencontre pendant la RE :

  1. **LE REGISTRE**, dans le meme commit -- `TARGETING_OPTIONS` (forme PRESET+FLAGS : le litteral
     visible n'est PAS le masque) ET `ABILITY_ATTACK_TYPE`, avec la MIGRATION hors de
     `TARGETING_OPTIONS_UNPORTED` (contrat de DISJONCTION). Un masque absent => gate 0 = permissif.
  2. **LA STRUCTURE ET L'ORDRE DE L'ARBRE.** Les cinq feuilles ne commutent pas : poser l'override
     avant le bond changerait l'equipe vue par le calcul de degat ; retirer le bond avant
     l'override rendrait l'unite a son camp en portant encore des degats ecrases.
  3. **`ChildrenOf` N'EST PAS `Children`.** Deux primitives natives HOMONYMES : `DSLFactory$$
     Children` (sans argument, l'accumulateur des summons du CAST) et `DSLSelectors$$Children(
     parent)` (scope sur un parent). 1101 appelle la SECONDE, et ne spawne rien -- brancher la
     premiere rend un selecteur toujours VIDE, sans erreur.
  4. **LA BRANCHE `Immune` NE PROTEGE QUE LA CIBLE.** `If(HasTrait(Target, Immune),
     Alive(Children(Target)), Target + Alive(Children(Target)))` : les summons d'une cible Immune
     restent possedes.
  5. **L'ORDRE DES ARGUMENTS DE `PercentageOfAttackCappedAtMax`.** La signature native est
     `(unit, statPart, maxAmount, percentage, roundingRule)` : intervertir `maxDmg` et `dmgPct`
     donnerait `min(100, 4001% x ATK)` = **100 degats plats**, une valeur PLAUSIBLE qu'aucun ordre
     de grandeur ne trahirait sur un point de mesure unique. Et `statPart = INITIAL` (pas CURRENT)
     evite que l'amount depende de l'override qu'il alimente.
  6. **LES DEUX GATES D'IDEMPOTENCE DE L'OWNER-SWAP SONT ASYMETRIQUES.** `ChangeUnitOwner` refuse
     une unite DEJA possedee (sinon l'owner d'origine est PERDU) ; `ResetUnitOwner` refuse une
     unite qui ne l'est PAS (sinon un retrait en double fabrique un owner).
  7. **LA PREFERENCE DE `GetPreferredAttackTarget` EST UN REPLI, PAS UN FILTRE DUR.**
     `chosen = (l2.Count > 0) ? l2 : l1` -- si TOUS les candidats sont deja possedes, on frappe
     quand meme. Un port qui filtrerait durement ne frapperait plus rien au 2e cast.

Aucune valeur de gameplay n'est ecrite en dur : les magnitudes sont re-derivees du gameconfig, et
seuls la STRUCTURE, les RAPPORTS et les FERMETURES sont assertes -- un rebalancement du jeu ne doit
pas rougir ici, un terme perdu du port, si.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe `ABILITY_CLASSES` (donc tout le registre
    # d'abilities), la factory d'effets, les selecteurs, les formules et les Operations -- sa
    # fermeture d'import couvre l'essentiel de `engine/**`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- AUCUNE valeur n'est figee depuis le binaire : le masque est compare a une
    # composition de MEMBRES d'enum (pas a `0x200004002` en litteral), les magnitudes viennent du
    # gameconfig. Ce qui est fige, ce sont les STRUCTURES lues au decompile.
    "build": False,
    # `toujours: True` : offline, aucun runner, ~1 s. Le cout de le rejouer a chaque passe est
    # negligeable devant ce qu'il garde -- et `perimetre()` ne lit PAS `toujours`, les deux crans
    # sont INDEPENDANTS (#486-r15).
    "toujours": True,
    "raison": "Gardes OFFLINE de 1101 : registre (masque PRESET+FLAGS + attack type + migration "
              "hors UNPORTED), structure ET ordre de l'arbre DSL, discrimination "
              "ChildrenOf/Children, gate Immune partiel, ordre des arguments de la formule de "
              "degat, les deux gates ASYMETRIQUES de l'owner-swap, et le REPLI de la preference "
              "de cible. Chacun est un piege ou un port faux resterait vert ailleurs.",
}

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.stats import StatPart, StatType
from engine.entities.traits.unit_trait import UnitTrait

ABILITY = int(ActiveAbilityType.AttemptedPossession)          # 1101 = 0x44d
POSSESSED = int(EffectType.AttemptedPossession_Possessed)     # 0x4b9 = 1209
DMG_OVERRIDE = int(EffectType.AttemptedPossession_DmgOverride)  # 0x4ba = 1210


# ---------------------------------------------------------------------------------------------
# Substrat minimal partage -- aucun runner, aucun RPC.
# ---------------------------------------------------------------------------------------------
class _Entity:
    def __init__(self, comps):
        self._c = {type(c): c for c in comps}

    def get_component(self, cls):
        return self._c.get(cls)


class _State:
    def __init__(self, entities):
        self.entities = entities
        self.board = None
        self.effects = None

    def get_entity(self, uid):
        return self.entities.get(uid)


def _etat_owner():
    """Deux unites de camps opposes : `1` = le caster (team 1 / player 3), `2` = la cible
    (team 2 / player 4). Le minimum que lisent `ChangeUnitOwnerOperation` / `ResetUnitOwnerOperation`."""
    from engine.runner.components import OwnerComponent
    return _State({1: _Entity([OwnerComponent(1, 3)]),
                   2: _Entity([OwnerComponent(2, 4)])})


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- LE REGISTRE (piege 1)
# ---------------------------------------------------------------------------------------------
def test_1101_est_au_registre_avec_son_masque_et_son_attack_type():
    """Entrer dans `ABILITY_CLASSES` sans masque = `get_invalid_target_reason` rend 0 => AUCUN
    gate, et le moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert ABILITY in ABILITY_CLASSES, "1101 doit etre au registre (sinon NO-OP silencieux)"
    cls = ABILITY_CLASSES[ABILITY]
    assert getattr(cls, "TARGETING_OPTIONS", None) is not None, \
        "masque ABSENT => gate 0 = degradation PERMISSIVE, invisible en self-play"
    assert ActiveAbilityType.AttemptedPossession in ABILITY_ATTACK_TYPE, \
        "ABILITY_ATTACK_TYPE est l'autre donnee OBLIGATOIRE du registre (probe_120 etape 0)"


def test_le_masque_est_le_OU_du_preset_et_des_flags_pas_le_litteral_visible():
    """FORME PRESET + FLAGS. `...AttemptedPossessionAbility$$.ctor` recopie `<TargetingOptions
    statics>+0x180` (rules `0x4002`) puis `TargetingOptions..ctor(&opts, &preset, 0x200000002)`.

    Le litteral `0x200000002` porte `0x2`, mais ce bit etait DEJA dans le preset : recopier le
    litteral comme masque effectif PERDRAIT `TargetIsEnemy` (`0x4000`) -- l'ability accepterait
    alors un ALLIE comme cible, sans erreur.

    Les trois bits sont nommes par leurs MEMBRES (jamais l'ordinal) : un ordinal juste aujourd'hui
    devient faux au changement de build, en silence."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    opts = ABILITY_CLASSES[ABILITY].TARGETING_OPTIONS
    attendu = int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.TargetIsNotAnObject)
    assert int(opts.rules) == attendu, (
        "masque effectif = preset (0x4002) OU flags (0x200000002) ; obtenu %s attendu %s"
        % (hex(int(opts.rules)), hex(attendu)))
    # Decomposition EXHAUSTIVE : aucun bit residuel, aucun bit manquant.
    assert int(opts.rules) & int(TR.TargetIsEnemy), \
        "TargetIsEnemy vient du PRESET, pas du litteral -- le perdre accepterait un ALLIE"
    assert not opts.self_cast, "isSelfCasting = 0 (2e argument du ctor natif)"


def test_1101_a_MIGRE_hors_de_la_table_de_repli():
    """CONTRAT DE DISJONCTION : une ability au registre porte son masque sur SA classe. La laisser
    dans les DEUX endroits est le gisement qui a rendu `master` rouge trois commits durant
    (`test_targeting_options_sources`, garde d'EXISTENCE aveugle a la DOUBLE declaration)."""
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    assert ActiveAbilityType.AttemptedPossession not in TARGETING_OPTIONS_UNPORTED, \
        "1101 est portee : son masque vit sur la classe, plus dans la table de repli"


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- STRUCTURE ET ORDRE DE L'ARBRE (piege 2)
# ---------------------------------------------------------------------------------------------
def _feuilles(noeud):
    """Aplatit un arbre de `Seq` (le mirror commun d'`op_Addition` et `op_BitwiseAnd`) en la liste
    ORDONNEE de ses feuilles."""
    from engine.entities.behaviours import Seq
    if isinstance(noeud, Seq):
        return _feuilles(noeud.left) + _feuilles(noeud.right)
    return [noeud]


def test_l_arbre_a_CINQ_feuilles_dans_l_ordre_natif_exact():
    """`Execute( (((bond + ovr) + ai) + rmOvr) & rmBond )` -- l'ordre est OBSERVABLE :

      * le bond (donc `ChangeUnitOwner`) doit preceder l'override de degat, sinon le calcul de
        degat de l'attaque commandee verrait l'ANCIENNE equipe ;
      * l'action IA doit suivre les deux poses, sinon elle frappe sans les degats ecrases ;
      * le retrait du BOND est le DERNIER : rendre l'unite a son camp avant de retirer l'override
        la laisserait un instant chez elle avec des degats ecrases.
    """
    from engine.runner.abilities.behaviours.ai_control import PerformAIAbility
    from engine.runner.abilities.behaviours.effects import AddBondEffect, RemoveEffect
    from engine.runner.abilities.behaviours.stats import AddStatOverrideEffect
    from engine.runner.abilities.loki.attempted_possession import (attempted_possession_targets,
                                                                   attempted_possession_tree)
    f = _feuilles(attempted_possession_tree(attempted_possession_targets()))
    assert len(f) == 5, "cinq feuilles natives, obtenu %d : %r" % (len(f), [type(x).__name__ for x in f])
    assert isinstance(f[0], AddBondEffect) and f[0].effect_type == POSSESSED
    assert isinstance(f[1], AddStatOverrideEffect) and f[1].effect_type == DMG_OVERRIDE
    assert isinstance(f[2], PerformAIAbility)
    assert isinstance(f[3], RemoveEffect) and f[3].effect_type == DMG_OVERRIDE
    assert isinstance(f[4], RemoveEffect) and f[4].effect_type == POSSESSED


def test_le_bond_est_bonde_au_CASTER_et_dure_en_TOURS_pas_en_ROUNDS():
    """`AddBondEffect(0x4b9, stateRef, source = Caster, targets = possedes, bondedEntity = Caster,
    turns = <DSLFormulas+0x20 = Constant(1)>)`.

    Le `bondedEntity` est ce que `ApplyInternal` passe a `ChangeUnitOwner` comme NOUVEAU
    proprietaire : le poser sur la cible ferait << se posseder soi-meme >> (no-op) au lieu de
    retourner l'unite.

    Et la surcharge est celle a `turns` (tranchee par ses XREFS ENTRANTES : l'autre prend
    `options`) -- passer la duree en `rounds` la DOUBLERAIT via `TurnsFromRounds`."""
    from engine.entities.selectors.tiles import Caster
    from engine.runner.abilities.loki.attempted_possession import (POSSESSION_TURNS,
                                                                   attempted_possession_targets,
                                                                   attempted_possession_tree)
    bond = _feuilles(attempted_possession_tree(attempted_possession_targets()))[0]
    assert isinstance(bond.bonded_ref, Caster), \
        "bondedEntity = Caster@sel+0x48 : c'est le NOUVEAU proprietaire du swap"
    assert isinstance(bond.source_ref, Caster), "source = Caster@sel+0x48"
    assert bond.duration_turns == POSSESSION_TURNS and bond.duration_rounds is None, \
        "surcharge a `turns` (Constant(1)), pas a `rounds` -- sinon la duree double"


def test_le_perform_ai_ability_porte_ses_QUATRE_parametres_natifs():
    """`PerformAIAbility(unit, getAbilityType, allowOnlyMove = 0, overrideMovement, utilityEntity =
    Owner, customUtility)`. `allowOnlyMove = 1` ajouterait le `MovementActionGenerator` : l'unite
    possedee pourrait choisir un DEPLACEMENT PUR au lieu d'attaquer."""
    from engine.entities.selectors.accessors import Owner
    from engine.runner.abilities.loki.attempted_possession import (attempted_possession_targets,
                                                                   attempted_possession_tree)
    ai = _feuilles(attempted_possession_tree(attempted_possession_targets()))[2]
    assert ai.allow_only_move is False, "litteral `0` du call-site natif"
    assert ai.override_movement is not None, \
        "sans overrideMovement, un summon possede n'approcherait pas (i2 : will move before attacking)"
    assert isinstance(ai.utility_entity, Owner), "utilityEntity = Owner@sel+0x30"


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- `ChildrenOf` N'EST PAS `Children` (piege 3)
# ---------------------------------------------------------------------------------------------
class _Ctx:
    """Contexte DSL minimal : le domaine d'unites + l'accumulateur de summons du cast."""
    def __init__(self, units, children=(), target=None, has_trait=None):
        self.units = list(units)
        self.children = list(children)
        self.target = target
        self.has_trait = has_trait


def test_childrenof_lit_le_parentId_la_ou_children_lit_l_accumulateur_du_cast():
    """LE piege qui rendrait TOUT le sous-arbre de selection VIDE, sans erreur.

    1101 ne spawne RIEN : `ctx.children` (l'accumulateur alimente par la feuille `SpawnUnit`) est
    donc vide a tout instant du cast. Le natif appelle `DSLSelectors$$Children(parent)`, qui lit le
    lien `parentId` -- ici, les summons de la CIBLE.
    """
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Children, ChildrenOf
    cible = {"id": 10}
    summon = {"id": 11, "parentId": 10}
    autre = {"id": 12, "parentId": 99}          # enfant de QUELQU'UN D'AUTRE
    ctx = _Ctx([cible, summon, autre], children=[], target=cible)
    assert [u["id"] for u in ChildrenOf(Target()).select(ctx)] == [11], \
        "ChildrenOf(Target) = les unites dont la CIBLE est le parent"
    assert Children().select(ctx) == [], \
        "Children (sans argument) = l'accumulateur du CAST -- vide ici, et c'est le point"


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- LE GATE `Immune` NE COUVRE QUE LA CIBLE (piege 4)
# ---------------------------------------------------------------------------------------------
def _selection(cible_immune: bool, cible_est_object: bool = False):
    """Evalue `attempted_possession_targets()` sur une cible + un summon vivant.

    ⚠ **LE SUMMON PORTE LE TRAIT `Summon`, ET C'EST CE QUI REND LA GARDE DISCRIMINANTE.** Sans lui,
    la contre-epreuve mesurait que le test restait VERT sous la mutation << branche VRAIE =
    `UnitsWithoutTrait(enfants, Summon)` >> : le filtre parasite ne retirait rien, donc la garde
    ne gardait rien. C'est aussi le cas REEL (i2 : << any **Summons** it has summoned >>)."""
    from engine.entities.selectors.accessors import Target
    from engine.runner.abilities.loki.attempted_possession import attempted_possession_targets
    cible = {"id": 10, "alive": True, "hp": 10}
    summon = {"id": 11, "parentId": 10, "alive": True, "hp": 5}
    noms = {10: set(), 11: {UnitTrait.Summon.name}}
    if cible_immune:
        noms[10].add(UnitTrait.Immune.name)
    if cible_est_object:
        noms[10].add(UnitTrait.Object.name)

    def _has_trait(unit, trait_id):
        uid = unit.get("id") if isinstance(unit, dict) else unit
        from engine.entities.traits.unit_trait import trait_name
        return trait_name(trait_id) in noms.get(uid, set())

    ctx = _Ctx([cible, summon], target=cible, has_trait=_has_trait)
    return [u["id"] for u in attempted_possession_targets().select(ctx)]


def test_une_cible_NON_immune_est_possedee_avec_ses_summons():
    assert _selection(cible_immune=False) == [10, 11], \
        "`Target + Alive(Children(Target))` -- la cible D'ABORD (ordre de l'union native)"


def test_une_cible_IMMUNE_est_exclue_mais_PAS_ses_summons():
    """La branche VRAIE du `If` natif ne garde QUE `Alive(Children(Target))`. Un port qui rendrait
    la selection VIDE sur une cible Immune perdrait la possession des summons -- et le gate
    dynamique, lui, l'AUTORISE explicitement (il ne refuse que si les summons vivants manquent)."""
    assert _selection(cible_immune=True) == [11], \
        "cible Immune retiree, ses summons RESTENT possedes"


def test_le_filtre_de_trait_final_retire_les_OBJECT_pas_les_SUMMON():
    """`UnitsWithoutTrait(..., 0xd = Object)` -- le trait `2` (`Summon`) sert AILLEURS (le budget de
    deplacement). Confondre les deux inverserait exactement le comportement decrit par l'i2 :
    << The target and any **Summons** it has summoned become possessed >>."""
    assert _selection(cible_immune=False, cible_est_object=True) == [11], \
        "une cible `Object` est retiree par le filtre final ; le summon reste"


# ---------------------------------------------------------------------------------------------
# ETAGE 5 -- LA FORMULE DE DEGAT (piege 5)
# ---------------------------------------------------------------------------------------------
class _Cfg:
    """`AbilityConfiguration.GetVariableForLevel(key, level)` -- valeurs re-derivees du gameconfig,
    jamais ecrites en dur."""
    def __init__(self, table):
        self.table = table

    def get_variable_for_level(self, key, level, default=0):
        return self.table.get(key, default)


class _FCtx:
    def __init__(self, subject, atk_initial, atk_current, config, level=50):
        self.subject = subject
        self.units = [subject]
        self.ability_level = level
        self.config = config
        self._atk = {int(StatPart.INITIAL): atk_initial, int(StatPart.CURRENT): atk_current}

    def get_stat(self, unit, stat_type, variant=0, level=None):
        assert int(stat_type) == int(StatType.ATTACK)
        return self._atk[int(variant)]


def _gameconfig_vars():
    import gameconfig as GC
    a = GC.ability("AttemptedPossession")
    v = a["variables"]
    return {"dmgPct": v["dmgPct"][-1], "maxDmg": v["maxDmg"][-1]}


def test_le_degat_est_min_maxDmg_et_pct_de_l_ATTACK_INITIALE():
    """`min( maxDmg , dmgPct% x StatAmount(It, ATTACK, INITIAL) )`.

    ⚠ L'INTERVERSION `maxAmount`/`percentage` est le piege : elle donnerait `min(dmgPct,
    maxDmg% x ATK)` = `min(100, ...)` = **100 degats plats**, une valeur PLAUSIBLE. Le montage la
    rend distinguable : on choisit une ATTACK telle que `dmgPct% x ATK` soit tres au-dessus de
    `dmgPct` et tres en-dessous de `maxDmg`, donc les deux ordres donnent des resultats a plus
    d'un ordre de grandeur d'ecart.

    ⚠ Et `statPart = INITIAL` : l'ATTACK COURANTE est deliberement differente ici. Lire CURRENT
    ferait dependre l'amount de l'override qu'il alimente."""
    from engine.runner.abilities.loki.attempted_possession import attempted_possession_damage
    g = _gameconfig_vars()
    pct, maxd = int(g["dmgPct"]), int(g["maxDmg"])
    atk_init = 500
    ctx = _FCtx({"id": 10}, atk_initial=atk_init, atk_current=99999, config=_Cfg(g))
    attendu = min(maxd, pct * atk_init // 100)
    obtenu = int(attempted_possession_damage().evaluate(ctx))
    assert obtenu == attendu, (
        "min(maxDmg=%d, dmgPct=%d%% x ATK_INITIAL=%d) attendu %d, obtenu %d -- une INTERVERSION "
        "des deux ConfigVar rendrait min(%d, ...) = %d"
        % (maxd, pct, atk_init, attendu, obtenu, pct, min(pct, maxd * atk_init // 100)))
    assert obtenu != min(pct, maxd * atk_init // 100), \
        "le montage doit DISTINGUER les deux ordres d'arguments (sinon la garde est vide)"


def test_le_cap_maxDmg_MORD_sur_une_ATTACK_enorme():
    """Le second regime de la meme formule : sans le `Min`, une unite a tres haute ATTACK
    infligerait `dmgPct% x ATK` sans plafond. i2 : << to a maximum of 4001 Damage per hit >>."""
    from engine.runner.abilities.loki.attempted_possession import attempted_possession_damage
    g = _gameconfig_vars()
    maxd = int(g["maxDmg"])
    ctx = _FCtx({"id": 10}, atk_initial=10 ** 6, atk_current=0, config=_Cfg(g))
    assert int(attempted_possession_damage().evaluate(ctx)) == maxd, \
        "le cap `maxDmg` doit MORDRE (sinon le `Min` a saute)"


# ---------------------------------------------------------------------------------------------
# ETAGE 6 -- LE BUDGET DE DEPLACEMENT
# ---------------------------------------------------------------------------------------------
class _MCtx:
    def __init__(self, actor, est_summon, movement):
        self.actor = actor
        self.units = [actor]
        self._summon = est_summon
        self._mv = movement

    def has_trait(self, unit, trait_id):
        from engine.entities.traits.unit_trait import trait_name
        return self._summon and trait_name(trait_id) == UnitTrait.Summon.name

    def get_stat(self, unit, stat_type, variant=0, level=None):
        assert int(stat_type) == int(StatType.MOVEMENT)
        return self._mv


@pytest.mark.parametrize("est_summon,attendu", [(True, 4), (False, 0)])
def test_le_budget_de_deplacement_n_est_ouvert_QUE_pour_un_summon(est_summon, attendu):
    """`ConditionalAmount(HasTrait(Actor, Summon), StatAmount(Actor, MOVEMENT), Constant(0))`.

    i2 : << Possessed **Summons** will move before attacking >>. Un possede NON-summon a `0` = sa
    tuile COURANTE pour seul domaine d'action ; ouvrir le budget pour tout le monde ferait
    approcher des unites que le natif garde sur place."""
    from engine.runner.abilities.loki.attempted_possession import attempted_possession_movement
    ctx = _MCtx({"id": 11}, est_summon, movement=4)
    assert int(attempted_possession_movement().evaluate(ctx)) == attendu


# ---------------------------------------------------------------------------------------------
# ETAGE 7 -- L'OWNER-SWAP ET SES DEUX GATES ASYMETRIQUES (piege 6)
# ---------------------------------------------------------------------------------------------
def test_le_swap_bascule_equipe_ET_player_et_le_revert_restaure_a_l_identique():
    """`ChangeUnitOwner(target, referenceUnit)` puis `ResetUnitOwner(target)`.

    Le natif ne stocke que le player entity id et derive l'equipe (`PlayerComponent.Team`) ; le
    port n'a pas d'entite-player, il bascule donc les DEUX -- meme derivation, materialisee. Le
    couple restaure doit etre BIT-IDENTIQUE : c'est ce que garde ce test."""
    from engine.runner.components import OwnerComponent
    from engine.runner.operations.change_unit_owner import (ChangeUnitOwnerOperation,
                                                            ResetUnitOwnerOperation,
                                                            is_owner_overridden)
    st = _etat_owner()
    oc = st.get_entity(2).get_component(OwnerComponent)
    avant = (oc.team, oc.player)
    assert not is_owner_overridden(st, 2)
    assert ChangeUnitOwnerOperation.execute(st, 2, 1) is True
    assert (oc.team, oc.player) == (1, 3), "la cible passe sous le camp du CASTER"
    assert is_owner_overridden(st, 2)
    assert ResetUnitOwnerOperation.execute(st, 2) is True
    assert (oc.team, oc.player) == avant, "revert BIT-IDENTIQUE"
    assert not is_owner_overridden(st, 2)


def test_un_second_swap_sur_une_unite_DEJA_possedee_est_refuse():
    """Gate `IsOwnerOverridden` de `ChangeUnitOwnerOperation$$Execute` (log + return).

    Sans lui, `overridden_from` serait ECRASE par le camp COURANT (= celui du 1er posseur) et
    l'unite ne reviendrait JAMAIS chez elle. Regime atteignable : deux casts de 1101 sur la meme
    cible, ou le trigger `On(UnitAdded)` reposant l'effet."""
    from engine.runner.components import OwnerComponent
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    st = _etat_owner()
    oc = st.get_entity(2).get_component(OwnerComponent)
    ChangeUnitOwnerOperation.execute(st, 2, 1)
    assert ChangeUnitOwnerOperation.execute(st, 2, 1) is False, \
        "un second swap DOIT etre refuse (sinon l'owner d'origine est PERDU)"
    assert oc.overridden_from == (2, 4), "l'origine reste celle du PREMIER swap"


def test_un_revert_sur_une_unite_NON_possedee_est_refuse():
    """Gate `!IsOwnerOverridden` de `ResetUnitOwnerOperation$$Execute` -- l'asymetrique du
    precedent. Sans lui, un double retrait fabriquerait un owner a partir de rien."""
    from engine.runner.operations.change_unit_owner import ResetUnitOwnerOperation
    st = _etat_owner()
    assert ResetUnitOwnerOperation.execute(st, 2) is False, \
        "rien a defaire => refus, pas de mutation"


def test_l_effet_1209_est_le_SEUL_a_declarer_l_owner_swap():
    """La part DATA `BaseEffect.overrides_unit_owner()` est le GATE de l'accroche imperative. Un
    effet qui la declarerait par erreur retournerait son porteur a chaque pose."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.possession import AttemptedPossessionPossessedEffect
    declarants = {n for n, c in EFFECT_CLASSES.items() if c(name=n).overrides_unit_owner()}
    assert declarants == {EffectType.AttemptedPossession_Possessed.name}, \
        ("un SEUL effet natif appelle ChangeUnitOwner dans son ApplyInternal ; declarants : %r"
         % (sorted(declarants),))
    assert AttemptedPossessionPossessedEffect(
        name=EffectType.AttemptedPossession_Possessed.name).overrides_unit_owner() is True


# ---------------------------------------------------------------------------------------------
# ETAGE 8 -- LA PREFERENCE DE CIBLE EST UN REPLI (piege 7)
# ---------------------------------------------------------------------------------------------
def test_la_preference_unpossessed_se_REPLIE_quand_tous_sont_deja_possedes(monkeypatch):
    """`chosen = (l2.Count > 0) ? l2 : l1` -- LE point ou << preferring >> se distingue d'un filtre.

    Montage : DEUX candidats, tous DEUX deja possedes. Un filtre dur rendrait `None` (aucune
    attaque) ; le natif frappe quand meme le plus proche. C'est le regime du SECOND cast, ou de la
    possession de plusieurs unites qui se voient entre elles."""
    import engine.runner.abilities.loki.attempted_possession as AP
    monkeypatch.setattr("engine.runner.abilities.targeting.valid_normal_attack_targets",
                        lambda st, uid: [20, 21])
    monkeypatch.setattr(AP, "_has_trait", lambda st, uid, t: False)
    monkeypatch.setattr(AP, "_has_effect", lambda st, uid, e: True)       # TOUS possedes
    monkeypatch.setattr(AP, "_nearest_of", lambda st, uid, cands: (min(cands) if cands else None))
    st = _etat_owner()
    st.entities[11] = _Entity([])
    assert AP.attempted_possession_preferred_target(st, 1, 11) == 20, \
        "repli sur la liste NON filtree : un filtre dur rendrait None (plus aucune attaque)"


def test_les_deja_possedes_sont_ECARTES_quand_il_reste_un_candidat_libre(monkeypatch):
    """L'autre moitie du meme `?:` : des qu'UN candidat est libre, les possedes sortent. Sans le
    filtre `b__2`, deux unites possedees s'entre-tueraient au lieu de frapper l'ennemi."""
    import engine.runner.abilities.loki.attempted_possession as AP
    monkeypatch.setattr("engine.runner.abilities.targeting.valid_normal_attack_targets",
                        lambda st, uid: [20, 21])
    monkeypatch.setattr(AP, "_has_trait", lambda st, uid, t: False)
    monkeypatch.setattr(AP, "_has_effect", lambda st, uid, e: uid == 20)  # 20 possede, 21 libre
    monkeypatch.setattr(AP, "_nearest_of", lambda st, uid, cands: (min(cands) if cands else None))
    st = _etat_owner()
    st.entities[11] = _Entity([])
    assert AP.attempted_possession_preferred_target(st, 1, 11) == 21, \
        "le candidat DEJA possede (20) doit sortir tant qu'un libre (21) existe"


def test_les_OBJECT_sont_ecartes_avant_meme_la_preference(monkeypatch):
    """`b__5_1` = `HasTrait(u, 0xd = Object) ^ 1`, applique AVANT `b__2` : un decor n'est jamais
    une cible, meme quand tous les autres candidats sont possedes."""
    import engine.runner.abilities.loki.attempted_possession as AP
    monkeypatch.setattr("engine.runner.abilities.targeting.valid_normal_attack_targets",
                        lambda st, uid: [20, 21])
    monkeypatch.setattr(AP, "_has_trait",
                        lambda st, uid, t: (uid == 20 and int(t) == int(UnitTrait.Object)))
    monkeypatch.setattr(AP, "_has_effect", lambda st, uid, e: True)       # tous possedes
    monkeypatch.setattr(AP, "_nearest_of", lambda st, uid, cands: (min(cands) if cands else None))
    st = _etat_owner()
    st.entities[11] = _Entity([])
    assert AP.attempted_possession_preferred_target(st, 1, 11) == 21, \
        "l'Object (20) est ecarte par b__5_1, AVANT le repli de b__2"


def test_le_custom_utility_rend_None_quand_aucune_cible_preferee(monkeypatch):
    """`GetAttackCustomUtility` : `if (target == null) return null` -- AUCUNE contrainte, et c'est
    ce qui fait de la contrainte une EXCLUSION legitime quand elle existe (le natif ne fabrique une
    `UtilityDefinition` que pour CONTRAINDRE)."""
    import engine.runner.abilities.loki.attempted_possession as AP
    monkeypatch.setattr(AP, "attempted_possession_preferred_target", lambda st, c, u: None)
    assert AP.attempted_possession_custom_utility(_etat_owner(), 1)(_etat_owner(), 11) is None


# ---------------------------------------------------------------------------------------------
# ETAGE 9 -- LA FACE DECISION
# ---------------------------------------------------------------------------------------------
def test_le_playbook_1101_est_au_registre_avec_son_plancher():
    """`MIN_UTILITY = 1` (le `.cctor`) et l'utilite PLANCHER `1` : le port ne REFUSE jamais un cast
    que le natif accepterait. Rendre `None` faute de mesure aurait rendu l'ability INCASTABLE par
    l'IA -- un no-op de plus, exactement ce que cette tranche ferme.

    ⚠ CE QUE `#590-r7` A CHANGE ICI, ET POURQUOI CE N'EST PAS UN TEST << ADAPTE POUR PASSER >>.
    Ce test passait un `ctx = None`, ce que le port tolerait tant que les deux `op_Increment`
    natifs n'etaient PAS portes : `evaluate_non_comparable` rendait alors le plancher sans rien
    lire. Depuis `#590-r7` les deux increments SONT portes, donc la fonction LIT le contexte -- un
    `None` n'est plus un contexte degrade, c'est un appel qui n'existe pas chez le natif.
    Le FAIT que ce test garde est inchange et reste asserte ci-dessous : **le plancher atteint
    `MIN_UTILITY`**, donc `Bucket$$AddAction` retient la candidate. Ce qui change est seulement
    l'argument par lequel on l'exerce -- un contexte VIDE (aucun substrat mesure), qui est
    precisement le regime ou les deux increments s'abstiennent."""
    from engine.playbook.noncomparable._base import NCContext
    from engine.playbook.noncomparable import PLAYBOOKS
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook
    pb = AttemptedPossessionPlaybook()
    vide = NCContext(uid=7, origin=(0, 0), reach_nc=[], epos=[], fpos=[], plan={},
                     hp_cur_by_id={})
    assert pb.ABILITY_ID == ABILITY
    assert pb.MIN_UTILITY == 1.0, "...AttemptedPossessionPlaybook$$.cctor = Fix64(1)"
    assert pb.evaluate_non_comparable((0, 0), 42, vide) >= pb.MIN_UTILITY, \
        "l'utilite PLANCHER doit atteindre le plancher, sinon Bucket.AddAction ne retient rien"
    assert pb.evaluate_non_comparable((0, 0), 42, vide) == pb.BASE_UTILITY, \
        "substrat entierement non mesure -> AUCUN increment : les deux termes sont des bornes INF"
    assert pb.evaluate_non_comparable((0, 0), None, vide) is None
    assert ABILITY in PLAYBOOKS and isinstance(PLAYBOOKS[ABILITY], AttemptedPossessionPlaybook), \
        "playbook non inscrit => l'IA ne propose jamais 1101 par cette voie"
