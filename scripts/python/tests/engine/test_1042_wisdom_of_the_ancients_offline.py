"""#1042 -- cliquet OFFLINE de la mythique `WisdomOfTheAncients` (1451) et de son effet 1445.

La face POSE est SEEDEE (`ABILITY_INIT_OWNER_EFFECTS`) et CONFRONTEE live
(`probe_1042_wisdom_of_the_ancients_live.py` : contre-bras `sans-mythique` vert, cinq bras). La
face DEGAT est PORTEE depuis #1042-r1 (`WisdomOfTheAncientsDamageReductionEffect`, canal AURA) ;
ce qui SEPARE ses trois etages de rarete vit dans
`tests/engine/runner/test_1038r1_1042r1_auras_mythiques_mow_offline.py`.

SIX ETAGES :
  1. l'ability est dans `ABILITY_INIT_OWNER_EFFECTS`, appariee a l'effet LU au call-site ;
  2. l'INSCRIPTION d'`EFFECT_CLASSES` est gardee AVEC ses deux proprietes (canal AURA, canal de
     rarete vivant) -- ce cran a d'abord garde le REFUS, et il a rougi DEUX fois en changeant de
     raison puis de sens (cf. sa docstring) ;
  3. les CINQ ordinaux ECRITS au site sont figes (`probe_313` compare le mirror au BUILD : il
     redevient vert apres un renumerotage, alors que l'ordinal ecrit au site, lui, a change) ;
  4. les types DECLARES de ces cinq positions sont ceux que le COMBAT declare -- LUS dans
     `frida/methods.tsv`, et l'etage ASSERTIONNE SON PROPRE NON-VIDE ;
  5. le PARENT de la classe d'ability est `BaseTriggeredAbility` -- LU dans `frida/classes.tsv`.
     C'est lui qui rend `$$CreateBehaviour`/`$$CreateTrigger` DECLARES (et non herites d'
     `AOwnerEffectTriggeredAbility`), donc lu tel quel ; si le parent changeait, la RE du site
     serait a refaire ;
  6. la variable que `ConfigVar(0x46)` lit existe toujours au gameconfig sous ce nom.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]            # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/entity_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Les etages 4 et 5 lisent `data/symbols/<build>/frida/{methods,classes}.tsv` et "
              "l'etage 6 le gameconfig -- un changement de build les concerne.",
}

ABILITY = "WisdomOfTheAncients"
EFFET = "WisdomOfTheAncients_DamageReduction"

#: LU au call-site, jamais deduit du nom :
#:   `...WisdomOfTheAncientsAbility$$CreateTrigger`   -> `OnOwnerSpecificAbilityInit(0x5ab)`
#:   `...WisdomOfTheAncientsAbility$$CreateBehaviour` -> `AddEffect(0x5a5, ...)`
ORDINAL_ABILITY = 0x5AB          # 1451
ORDINAL_EFFET = 0x5A5            # 1445

#: (module, enum, membre, ordinal ECRIT au site, methode native qui le DECLARE, nom du parametre).
#: Les cinq positions litterales de l'arbre, dans l'ordre du decompile.
SITES = (
    ("engine.entities.rarity", "Rarity", "Mythic", 5,
     "IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity", "rarity",
     "idun.meta.Rarity"),
    ("engine.entities.unit_selection_type", "UnitSelectionType", "OnlyAliveAndTargetable", 3,
     "IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity", "unitSelectionType",
     "IdunBattle.Entities.Enum.UnitSelectionType"),
    ("engine.entities.traits.unit_trait", "UnitTrait", "Hero", 0x10,
     "IdunBattleLogic.Entities.DSLSelectors.UnitsWithTrait", "trait",
     "IdunBattle.Entities.Enum.UnitTrait"),
    ("engine.entities.ability_variable_type", "AbilityVariableType", "dmgReductionPct", 0x46,
     "IdunBattleLogic.Entities.DSLFormulas.ConfigVar", "variableType",
     "IdunBattle.Configuration.AbilityVariableType"),
    ("engine.entities.entity_type", "EntityType", "Machine", 6,
     None, None, None),      # lu dans `EntityExtensions$$IsMachine` (comparaison a 6), pas un param
)


def _canal_rarete_existe() -> bool:
    """Le port a-t-il, pour une UNITE, un canal de rarete ? DERIVE, jamais enumere : on regarde le
    porteur de contexte d'unite lui-meme. Tant que c'est faux, les TROIS etages
    `UnitsWithRarity(Mythic)` du selecteur de 1445 sont inevaluables."""
    from engine.entities.unit_context import UnitContext
    return "rarity" in getattr(UnitContext, "__annotations__", {})


# ==================================== (1) la pose est seedee, appariee a l'effet LU au call-site

def test_ability_init_owner_effect_inscrite():
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    assert ABILITY in ABILITY_INIT_OWNER_EFFECTS, (
        f"{ABILITY} n'est plus dans ABILITY_INIT_OWNER_EFFECTS : l'owner-effect permanent pose a "
        f"l'init (`AddEffect(0x5a5, AbilityStateReference, source = Owner, targets = Owner)`) "
        f"n'est plus seede offline")
    assert ABILITY_INIT_OWNER_EFFECTS[ABILITY] == [EFFET], (
        f"{ABILITY} -> {ABILITY_INIT_OWNER_EFFECTS[ABILITY]} ; l'appariement LU au call-site de "
        f"`...WisdomOfTheAncientsAbility$$CreateBehaviour` est [{EFFET!r}]")
    # Les DEUX ordinaux sont FIGES ici parce qu'ils sont ECRITS aux sites cites (0x5ab / 0x5a5).
    assert int(getattr(TriggeredAbilityType, ABILITY)) == ORDINAL_ABILITY
    assert int(getattr(EffectType, EFFET)) == ORDINAL_EFFET


# ========================= (2) le refus d'EFFECT_CLASSES est CONDITIONNEL au canal de rarete

def test_effet_au_registre_sur_le_canal_aura():
    """REQUALIFIE PAR #1042-r1 -- ce cran a ROUGI DEUX FOIS, et les DEUX fois il a eu RAISON.

    Etat d'ORIGINE : il figeait le REFUS d'`EFFECT_CLASSES`, conditionnel au canal de rarete, et il
    etait ecrit pour rougir << dans les DEUX sens >>, le second etant le plus utile -- se taire le
    jour ou le capteur arriverait aurait laisse `#1042-r1` dormir.

    PREMIER rougissement (#999-r3-r1-r1) : les deux verrous d'origine etaient tombes (le canal de
    rarete, puis l'entree d'une MoW porteuse dans l'univers des agregateurs d'aura). La RAISON du
    refus avait change, pas le refus.

    SECOND rougissement (#1042-r1, CE COMMIT) : l'effet est PORTE. Ce cran change donc de SENS et
    garde desormais l'INSCRIPTION, plus les deux proprietes que l'inscription devait respecter :

      1. le canal est l'AURA (`create_aura_defense_damage_malus_for_ally`) et **PAS** celui du
         porteur -- l'inscrire sur `create_effect_damage_malus_for_defense` donnerait la reduction
         a la MoW elle-meme, que le natif ne lui accorde JAMAIS ;
      2. le canal de RARETE existe toujours -- s'il disparaissait, les TROIS etages
         `UnitsWithRarity(Mythic)` du selecteur redeviendraient inevaluables et le port
         redeviendrait PERMISSIF (l'aura protegerait tout ami adjacent a un ami Hero, Mythique ou
         non), SANS que rien d'autre ne rougisse.

    ⚠ CE QUI SEPARE VIT AILLEURS, et c'est voulu : les bras et contre-bras des trois etages sont
    dans `tests/engine/runner/test_1038r1_1042r1_auras_mythiques_mow_offline.py` (etages D/E/F),
    qui exhibe a chaque fois son TEMOIN NON NUL. Le rappel du piege reste ici : `rl_duel build`
    impose `targetRarity = 5` a toute unite normalisee, donc les trois etages y sont uniformement
    VRAIS (regime DEGENERE) -- on en sort par `--unit-stat "<vis>:Rarity=N"`. MESURE #1042 :
    `P1:Rarity=4` fait tomber le set a `{P2,P3}`, `P2:Rarity=4` le VIDE."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import EFFECT_CLASSES

    # Le canal de rarete, assertionne ici pour que son RETRAIT rougisse : le port redeviendrait
    # PERMISSIF en silence.
    assert _canal_rarete_existe(), (
        "`UnitContext` ne porte plus de rarete : le canal (#999-r3, capteur #1039) est retire, et "
        "les TROIS etages `UnitsWithRarity(Mythic)` du selecteur de 1445 redeviennent "
        "inevaluables. Relire case-999r3-canal-rarete.")
    assert EFFET in EFFECT_CLASSES, (
        f"{EFFET} est sorti d'EFFECT_CLASSES : la face DEGAT de la mythique redevient INERTE, sans "
        f"erreur ni trace. Relire case-1042-wisdom-of-the-ancients.md.")
    cls = EFFECT_CLASSES[EFFET]
    assert cls.create_aura_defense_damage_malus_for_ally \
        is not BaseEffect.create_aura_defense_damage_malus_for_ally, (
        f"{EFFET} n'implemente plus le canal AURA -- il serait inscrit et muet")
    assert cls.create_effect_damage_malus_for_defense \
        is BaseEffect.create_effect_damage_malus_for_defense, (
        f"{EFFET} implemente le canal du PORTEUR : la MoW se donnerait a elle-meme une reduction "
        f"que le natif ne lui accorde JAMAIS (terme PERMISSIF)")


# =================================================== (3) les ordinaux du site, FIGES au site

@pytest.mark.parametrize("site", SITES, ids=[s[2] for s in SITES])
def test_ordinaux_ecrits_au_site_figes(site):
    module, enum_nom, membre, ordinal = site[0], site[1], site[2], site[3]
    mod = __import__(module, fromlist=[enum_nom])
    vu = int(getattr(getattr(mod, enum_nom), membre))
    assert vu == ordinal, (
        f"{enum_nom}.{membre} = {vu} ; l'ordinal ECRIT au site du decompile cite par "
        f"`case-1042-wisdom-of-the-ancients.md` est {ordinal}. Regenerer le mirror ne suffit PAS : "
        f"c'est la RE ecrite qui doit etre relue.")


# ============ (4) le COMBAT declare bien ces types-la aux positions citees (methods.tsv)

def test_le_combat_declare_les_types_des_positions_citees():
    from symbols_layout import build_dir, current_build

    p = Path(build_dir(current_build())) / "frida" / "methods.tsv"
    if not p.exists():
        pytest.skip(f"table absente : {p}")
    attendus = {(s[4], s[5]): s[6] for s in SITES if s[4] is not None}
    # Les deux positions du POSEUR, en plus des quatre positions du selecteur/formule.
    attendus[("IdunBattleLogic.Entities.DSLTriggers.OnOwnerSpecificAbilityInit", "type")] = \
        "IdunBattle.Entities.Enum.TriggeredAbilityType"
    attendus[("IdunBattleLogic.Entities.DSLBehaviors.AddEffect", "effectType")] = \
        "IdunBattle.Entities.Enum.EffectType"

    vus: dict[tuple, set] = {}
    for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
        col = ligne.split("\t")
        if len(col) < 6:
            continue
        for param in col[5].split(","):
            nom, _, typ = param.partition(":")
            cle = (col[1], nom.strip())
            if cle in attendus:
                vus.setdefault(cle, set()).add(typ.strip())
    # ASSERTIONNER SON PROPRE NON-VIDE : un balayage qui ne trouve rien passerait pour vert.
    assert set(vus) == set(attendus), (
        f"positions introuvables dans {p.name} : trouvees={sorted(vus)} "
        f"attendues={sorted(attendus)}")
    for cle, typ in sorted(attendus.items()):
        assert vus[cle] == {typ}, (
            f"le type DECLARE de `{cle[1]}` sur `{cle[0]}` n'est plus unique/attendu : "
            f"{sorted(vus[cle])} (attendu {typ!r}). La VOIE ne dit pas l'enum, l'ORDINAL non plus "
            f"-- seul le type declare tranche.")


# ================================= (5) le PARENT de la classe d'ability (classes.tsv)

def test_le_parent_de_l_ability_est_base_triggered_ability():
    """`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, et NON `AOwnerEffectTriggeredAbility`.

    C'est ce qui fait que `$$CreateBehaviour` / `$$CreateTrigger` sont DECLARES par la classe et
    lus tels quels (comme `CabalOfSorcerers`), au lieu d'etre herites d'une base dont le corps est
    DEDUPLIQUE. Si le parent changeait, la RE du site serait a refaire."""
    from symbols_layout import build_dir, current_build

    p = Path(build_dir(current_build())) / "frida" / "classes.tsv"
    if not p.exists():
        pytest.skip(f"table absente : {p}")
    cible = "IdunBattleLogic.Entities.Abilities.Triggered.Loki.WisdomOfTheAncientsAbility"
    parents = {}
    for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
        col = ligne.split("\t")
        if len(col) >= 3 and col[0] == cible:
            parents[col[0]] = col[2]
    # NON-VIDE assertionne : une classe disparue rendrait ce test vert sans rien mesurer.
    assert cible in parents, f"{cible} absente de {p.name} -- la RE du site n'est plus ancree"
    assert parents[cible] == "IdunBattle.Entities.Abilities.BaseTriggeredAbility", (
        f"parent de {cible} = {parents[cible]!r} ; la RE de "
        f"`case-1042-wisdom-of-the-ancients.md` Sec.1 suppose `BaseTriggeredAbility` (deux "
        f"methodes "
        f"DECLAREES). Relire le site.")


# ============================ (6) la variable que `ConfigVar(0x46)` lit existe au gameconfig

def test_la_variable_de_magnitude_existe_au_gameconfig():
    import gameconfig

    cfg = gameconfig.ability(ABILITY) or {}
    variables = cfg.get("variables") or {}
    assert variables, f"aucune variable pour {ABILITY} au gameconfig -- rien n'est mesure ici"
    assert "dmgReductionPct" in variables, (
        f"`dmgReductionPct` (AbilityVariableType 0x46) a disparu des variables de {ABILITY} : "
        f"{sorted(variables)}. C'est CETTE cle que "
        f"`...WisdomOfTheAncients_DamageReductionEffect$$CreateEffectDamageMalusForDefense` lit "
        f"par `ConfigVar`.")
    paliers = variables["dmgReductionPct"]
    assert paliers and all(isinstance(v, (int, float)) for v in paliers), (
        f"paliers `dmgReductionPct` inexploitables : {paliers!r}")
