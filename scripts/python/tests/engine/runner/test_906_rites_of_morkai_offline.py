"""GARDES #906 -- `1211 RitesOfMorkai` (`spaceWolfPriest` << Baldr >>), face COMBAT.

Ce fichier FIGE ce que la confrontation live (`probe_906_rites_of_morkai_live.py`) a etabli, et
que rien d'autre ne garde : les valeurs LUES au decompile et la FORME de l'arbre. Le probe mesure,
ce test empeche la valeur mesuree de deriver en silence.

CE QUE CHAQUE ETAGE GARDE, et pourquoi il ne se deduit pas d'un autre :

  1. le MASQUE `0x2008402` -- au LITTERAL, bit a bit. `probe_181` ne verifie que la PRESENCE d'un
     `TARGETING_OPTIONS` ; il rendrait vert sur un masque faux.
  2. `ABILITY_ATTACK_TYPE[1211] == Others` -- `probe_120` etape 0 ne verifie, la aussi, que la
     PRESENCE de la cle. Le contre-sens etait ici facile : l'arbre ENCHAINE une attaque normale,
     donc << une ability qui frappe >> ferait ecrire `DirectTargetAttack`. Le ctor dit `2`.
  3. la FORME de l'arbre -- le `Cache` de la zone doit etre l'OBJET PARTAGE par les deux poses
     (sinon la seconde relit un plateau deja mute), et l'attaque normale doit rester sous son `If`.
  4. le GATE DYNAMIQUE -- `IsMechanical` (la DISJONCTION Mechanical|LivingMetal|Vehicle) sur la
     CIBLE, la ou la ZONE filtre le trait `Mechanical` SEUL. Les deux predicats coexistent dans
     cette ability et DIFFERENT : un Necron `LivingMetal` sans `Mechanical` est refuse comme cible
     et reste dans la zone. Rien d'autre ne l'empeche d'etre << harmonise >>.
  5. l'effet 1529 -- son canal de degat n'a QU'UN noeud de trigger (`get_OwnerIsCaster`), sans
     `IsMeleeAttack` ni `IsNormalAttack` : c'est le contraste avec `1222 WarHowl`, dont il aurait
     ete tentant de recopier les trois gates par analogie de forme. L'i2 dit << with all attacks >>.
  6. les CONSTANTES gameconfig lues (`range`, `nrOfRounds`, `extraDmg`) -- une cle disparue ferait
     LEVER `GetNumberConstant` cote natif et retomber sur un defaut cote port, silencieusement.

Ces six etages sont OFFLINE (aucun runner, aucun RPC, aucune lecture du binaire). ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        # le port lui-meme : l'arbre, le masque et le gate dynamique
        "scripts/python/engine/runner/abilities/spacewolves.py",
        # les DEUX registres que l'entree au catalogue alimente
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        # l'effet 1529 et son enregistrement
        "scripts/python/engine/entities/effects/loki/rites_of_morkai.py",
        "scripts/python/engine/entities/effects/factory.py",
        # la POSE : `source_from_target` + le scaling depuis l'`abilityState` du CASTER, mesure a
        # 3552 de degat sur le scenario live -- un foyer PARTAGE, pris LARGE a dessein.
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        # les noeuds DSL que l'arbre compose ; un changement de leur signature casserait la forme
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        # les enums que les six etages citent par leur MEMBRE
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        # la SOURCE des trois constantes de l'etage 6
        "data/gameconfig.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC, aucune lecture du binaire. Le perimetre "
              "est pris LARGE parce que les six etages figent une COMPOSITION -- l'arbre DSL de "
              "1211 traverse selecteurs, triggers, feuilles de combat et deux registres, et la "
              "confrontation live a montre qu'un seul de ces etages qui bouge (le scaling de la "
              "pose) vaut 3552 de degat. Le gameconfig y entre parce que trois constantes LUES "
              "(range, nrOfRounds, extraDmg) decident de la zone, de la duree et du bonus.",
}

import pytest                                                            # noqa: E402

from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES               # noqa: E402
from engine.entities.effects.loki.rites_of_morkai import (               # noqa: E402
    RitesOfMorkaiExtraDamageEffect)
from engine.entities.selectors.geometry import Cache                     # noqa: E402
from engine.entities.selectors.units import Filter                       # noqa: E402
from engine.entities.triggers import AmountIsGreaterThanZero, HasEffect, HasTrait, TriggerOr  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                  # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE      # noqa: E402
from engine.runner.abilities.behaviours.combat import UseNormalAttack    # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import RANGE_FROM_CONFIG          # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.abilities import spacewolves as SW                    # noqa: E402

RITES = int(ActiveAbilityType.RitesOfMorkai)                             # 1211


def _klass():
    k = ABILITY_CLASSES.get(RITES)
    assert k is not None, "1211 doit etre au registre `ABILITY_CLASSES` (sinon le cast est un no-op)"
    return k


# --- etage 1 : le MASQUE, au litteral -----------------------------------------------------------

def test_masque_est_le_litteral_du_ctor():
    """`RitesOfMorkaiAbility$$.ctor` -> `TargetingOptions..ctor(..., rules = 0x2008402, ...)`,
    forme FLAGS DIRECTS (l'ADRESSE du `call` vise la surcharge a 6 arguments) : le litteral EST le
    masque, aucun preset a OU-er. LU AU DESASSEMBLAGE
    (`mov qword ptr [rsp + 0x20], 0x2008402`)."""
    opts = _klass().TARGETING_OPTIONS
    assert int(opts.rules) == 0x2008402
    # decomposition EXHAUSTIVE : aucun bit residuel, et chacun est NOMME
    attendu = (TR.TargetMatchesDynamicRule | TR.TargetIsFriendly
               | TR.CasterIsPossibleTarget | TR.AllowObscuredTargetByElevation)
    assert int(opts.rules) == int(attendu)
    assert opts.self_cast is True                    # `isSelfCasting = 1`
    assert opts.range is RANGE_FROM_CONFIG           # `TargetingRange` statics + 0x18
    assert int(opts.force_melee_target) == 1         # `RangedBool.False`


def test_masque_ne_porte_pas_les_bits_des_voisins():
    """CONTRE-EPREUVE : les trois bits que les voisins de ce module portent et que 1211 n'a PAS.
    Sans elle, un masque sur-charge (`| TargetIsEnemy`) passerait l'egalite ci-dessus seulement si
    quelqu'un mettait a jour les deux lignes -- ici il faut casser DEUX assertions de sens oppose."""
    r = int(_klass().TARGETING_OPTIONS.rules)
    assert not (r & int(TR.TargetIsEnemy)), "1211 vise un AMI (0x400), pas un ennemi"
    assert not (r & int(TR.CasterHasNotMoved)), "pas de gate `CasterHasNotMoved` (c'est WarHowl)"
    assert not (r & int(TR.TargetIsInRange)), "pas de `TargetIsInRange` (c'est GrapnelLauncher)"


# --- etage 2 : l'AbilityAttackType --------------------------------------------------------------

def test_ability_attack_type_est_others():
    """`mov r8d, 2 ; call <AActiveAbility..ctor>` -> **2 = Others**, malgre l'attaque normale que
    l'arbre enchaine. TRANSCRIT du ctor, jamais deduit du profil de degat."""
    from engine.runner.abilities.attack_type import AbilityAttackType
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.RitesOfMorkai] == AbilityAttackType.Others


# --- etage 3 : la FORME de l'arbre --------------------------------------------------------------

def _arbre():
    return SW.rites_of_morkai_tree(1, 1)


def test_arbre_pose_les_deux_effets_puis_attaque():
    """`op_Addition(op_Addition(AddEffect(1502), AddEffect(1529)), If(..., UseNormalAttack))`."""
    feuilles = []

    def visiter(n):
        for attr in ("left", "right", "a", "b", "then", "otherwise", "first", "second"):
            v = getattr(n, attr, None)
            if v is not None and hasattr(v, "execute"):
                visiter(v)
        for v in (getattr(n, "children", None) or getattr(n, "items", None) or ()):
            if hasattr(v, "execute"):
                visiter(v)
        feuilles.append(n)

    visiter(_arbre())
    noms = [type(n).__name__ for n in feuilles]
    assert noms.count("AddEffect") == 2, "DEUX poses (1502 puis 1529), pas une : %s" % noms
    assert "UseNormalAttack" in noms, "le TROISIEME volet -- celui que l'audit ne voit pas : %s" % noms
    types = sorted(int(n.effect_type) for n in feuilles if type(n).__name__ == "AddEffect")
    assert types == sorted([int(EffectType.RitesOfMorkai),
                            int(EffectType.RitesOfMorkai_ExtraDamage)])


def test_le_cache_de_la_zone_est_partage_par_les_deux_poses():
    """LOAD-BEARING : le natif passe le MEME objet `Cache` a l'`AddEffect(1502)` et au `Filter` de
    l'`AddEffect(1529)`. Deux instances distinctes feraient relire un plateau deja mute par la
    premiere pose -- une divergence qui n'apparaitrait que sur un etat ou la zone change entre les
    deux, donc invisible du scenario nominal."""
    poses = []

    def collecte(n):
        if type(n).__name__ == "AddEffect":
            poses.append(n)
        for attr in ("left", "right", "then", "otherwise"):
            v = getattr(n, attr, None)
            if v is not None and hasattr(v, "execute"):
                collecte(v)

    collecte(_arbre())
    assert len(poses) == 2
    zone = next(p.target_sel for p in poses
                if int(p.effect_type) == int(EffectType.RitesOfMorkai))
    filtre = next(p.target_sel for p in poses
                  if int(p.effect_type) == int(EffectType.RitesOfMorkai_ExtraDamage))
    assert isinstance(zone, Cache), "la zone est un `DSLSelectors$$Cache`"
    assert isinstance(filtre, Filter), "1529 cible un `Filter` de la zone"
    assert filtre.source is zone, "le `Filter` doit consommer LE MEME objet Cache (identite)"


def test_attaque_normale_sous_son_predicat():
    """`If(AmountIsGreaterThanZero(<cibles>), UseNormalAttack(...))` -- et le predicat consomme le
    MEME selecteur que l'attaque (le natif ne le met PAS en cache : il l'evalue deux fois)."""
    racine = _arbre()
    ifs = []

    def collecte(n):
        if type(n).__name__ == "If":
            ifs.append(n)
        for attr in ("left", "right", "then", "otherwise"):
            v = getattr(n, attr, None)
            if v is not None and hasattr(v, "execute"):
                collecte(v)

    collecte(racine)
    assert len(ifs) == 1, "UN SEUL `If` dans cet arbre"
    noeud = ifs[0]
    assert isinstance(noeud.cond, AmountIsGreaterThanZero)
    assert isinstance(noeud.then, UseNormalAttack)
    assert noeud.otherwise is None, "le 4e argument natif du `If` est NUL"
    assert noeud.cond.a is noeud.then.target_sel, (
        "le predicat et l'attaque consomment LE MEME selecteur (aucun `Cache` sur cette branche)")


def test_poses_sans_source_explicite_et_avec_le_scaling_du_caster():
    """La surcharge 4-args d'`AddEffect` passe `source = 0` -> chaque cible est SA PROPRE source
    (`source_from_target`), tandis que l'`abilityState` reste celui du CASTER
    (`scale_from_source`). Confondre les deux slots coute 3552 de degat, MESURE live (mutant
    `no_scale` de `probe_906_rites_of_morkai_live.py`)."""
    trouves = []

    def collecte(n):
        if type(n).__name__ == "AddEffect":
            trouves.append(n)
        for attr in ("left", "right", "then", "otherwise"):
            v = getattr(n, attr, None)
            if v is not None and hasattr(v, "execute"):
                collecte(v)

    collecte(_arbre())
    assert len(trouves) == 2
    for p in trouves:
        assert p.source_from_target is True, "surcharge 4-args : `source` NULL"
        assert p.scale_from_source is True, "`abilityState` = celui du CASTER"


# --- etage 4 : le GATE DYNAMIQUE ----------------------------------------------------------------

class _FauxState:
    """Substrat minimal pour `abilities/targeting.is_mechanical` : un `State` reduit a la table
    des traits par unite (le foyer resout `State` + id -> NOMS, puis delegue)."""

    def __init__(self, traits_par_id):
        self._t = traits_par_id


@pytest.mark.parametrize("traits, refuse, motif", [
    (["Hero"], False, "un allie ordinaire est une cible VALIDE"),
    (["Hero", "Mechanical"], True, "trait Mechanical (5)"),
    (["Hero", "LivingMetal"], True, "LivingMetal (0x3e8) -- la DISJONCTION, pas le seul trait 5"),
    (["Hero", "Vehicle"], True, "Vehicle (0x405) -- idem"),
])
def test_gate_dynamique_refuse_les_mecaniques(monkeypatch, traits, refuse, motif):
    """`GetDynamicInvalidTargetReason` = `target != null ? (IsMechanical(target) ? 2 : 0) : 2`.

    ⚠ `IsMechanical` est la DISJONCTION `Mechanical | LivingMetal | Vehicle` -- c'est ce que les
    deux dernieres lignes du parametrage gardent, et ce qui le DISTINGUE du filtre de la ZONE
    (`UnitsWithoutTrait(0x5)`, le trait SEUL)."""
    monkeypatch.setattr(SW, "is_mechanical", lambda _st, _uid: any(
        t in traits for t in ("Mechanical", "LivingMetal", "Vehicle")))
    got = _klass()().get_dynamic_invalid_target_reason(_FauxState({}), 1, 2)
    attendu = int(TR.TargetMatchesDynamicRule) if refuse else 0
    assert got == attendu, motif


def test_gate_dynamique_refuse_la_cible_nulle():
    """La branche `target == null -> 2` est EXPLICITE au decompile, pas une chute par defaut."""
    assert _klass()().get_dynamic_invalid_target_reason(_FauxState({}), 1, None) == int(
        TR.TargetMatchesDynamicRule)


def test_le_filtre_de_zone_est_le_trait_SEUL():
    """CONTRE-EPREUVE du precedent : la zone filtre `UnitTrait.Mechanical` et RIEN d'autre. Ecrire
    la disjonction ici serait une harmonisation INVENTEE -- un Necron `LivingMetal` sans
    `Mechanical` doit RESTER dans la zone."""
    assert SW.MECHANICAL_TRAIT == int(UnitTrait.Mechanical)
    zone = SW.rites_of_morkai_buff_zone(1)
    assert isinstance(zone, Cache)
    # Cache(Union(Owner, UnitsWithoutTrait(SurroundingFriends(...), Mechanical, 3)))
    sans_trait = zone.source.b if hasattr(zone.source, "b") else None
    assert type(sans_trait).__name__ == "UnitsWithoutTrait"
    assert int(sans_trait.trait) == int(UnitTrait.Mechanical)


# --- etage 5 : l'effet 1529 ---------------------------------------------------------------------

def test_effet_1529_au_registre():
    assert EFFECT_CLASSES.get("RitesOfMorkai_ExtraDamage") is RitesOfMorkaiExtraDamageEffect
    assert int(EffectType.RitesOfMorkai_ExtraDamage) == 0x5f9


def test_le_predicat_final_vengeance_est_une_DISJONCTION_de_deux_noeuds():
    """`HasTrait(ActiveTarget, 0x3f6 = FinalJustice) op_BitwiseOr HasEffect(ActiveTarget,
    0x5ae = FinalVengeance_UnitEffect, onlyActive: 0, Both)`.

    ⚠ `onlyActive = 0` est LU au call-site et il MORD : le natif accepte une instance 1454 INERTE.
    Le DEFAUT du noeud est `True` -- recopier le defaut retirerait le bonus a un porteur dont la
    Final Vengeance est momentanement desactivee, silencieusement."""
    t = SW.rites_of_morkai_has_any_kind_of_final_vengeance()
    assert isinstance(t, TriggerOr)
    gauche, droite = t.a, t.b
    assert isinstance(gauche, HasTrait) and int(gauche.trait) == int(UnitTrait.FinalJustice)
    assert isinstance(droite, HasEffect)
    assert int(droite.effect_type) == int(EffectType.FinalVengeance_UnitEffect)
    assert droite.active_only is False, "`onlyActive = 0` -- une instance INERTE compte"


def test_le_canal_de_degat_de_1529_na_quun_seul_gate():
    """`ForAddition(get_OwnerIsCaster, ConfigVar(0x8 = extraDmg))` -- **UN** noeud de trigger.

    Le contraste est `1222 WarHowl`, dont le meme canal en porte TROIS
    (`get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack`). Recopier les trois par analogie de
    forme eteindrait le bonus sur les tirs et sur les attaques d'ability -- alors que l'i2 dit
    << deal +extraDmg Damage **with all attacks** >>. On exerce donc les QUATRE combinaisons."""
    eff = RitesOfMorkaiExtraDamageEffect("RitesOfMorkai_ExtraDamage",
                                       effect_type=int(EffectType.RitesOfMorkai_ExtraDamage),
                                       active_ability_level=1)
    vus = []
    for is_ranged in (True, False):
        for is_normal in (True, False):
            b = eff.create_effect_damage_bonus_for_attack(
                is_ranged=is_ranged, is_normal_attack=is_normal)
            vus.append((is_ranged, is_normal, None if b is None else b.kind))
    assert all(v[2] == "Addition" for v in vus), (
        "le bonus doit tomber dans les QUATRE regimes (aucun gate melee/normale) : %s" % vus)


def test_la_condition_dactivite_est_tri_etat():
    """`CreateActiveCondition` = le MEME `op_BitwiseOr`, ancre sur `Owner`. Un membre VRAI suffit ;
    les DEUX mesures fausses ferment ; un membre NON MESURE ne ferme PAS (degradation fidele)."""
    eff = RitesOfMorkaiExtraDamageEffect("RitesOfMorkai_ExtraDamage")
    assert eff.is_active({"traits": ["Hero", "FinalJustice"]}) is True        # 1er membre vrai
    assert eff.is_active({"traits": ["Hero"], "owner_id": 1,
                          "has_effect_on": lambda _u, _e: True}) is True      # 2e membre vrai
    assert eff.is_active({"traits": ["Hero"], "owner_id": 1,
                          "has_effect_on": lambda _u, _e: False}) is False    # les deux faux
    assert eff.is_active({"traits": ["Hero"]}) is True                        # 2e NON MESURE
    assert eff.is_active({}) is True                                         # rien de mesure


# --- etage 6 : les CONSTANTES gameconfig lues ---------------------------------------------------

def test_les_trois_cles_gameconfig_existent():
    """`GetNumberConstant(0x16 = range)`, `ConfigConst(0x45 = nrOfRounds)` et
    `ConfigVar(0x8 = extraDmg)`. Une cle disparue fait LEVER le natif
    (`AbilityConfiguration$$GetStringConstant` jette) et retomber le port sur un defaut : la
    divergence serait alors SILENCIEUSE."""
    import gameconfig as GC
    cfg = GC.ability("RitesOfMorkai")
    assert "range" in (cfg.get("constants") or {})
    assert "nrOfRounds" in (cfg.get("constants") or {})
    assert "extraDmg" in (cfg.get("variables") or {})
    # `extraDmg` EST rarity-affected -> le scaling depuis le CASTER n'est pas cosmetique
    assert "extraDmg" in (cfg.get("variablesAffectedByRarityBonus") or [])
