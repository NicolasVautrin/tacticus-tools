"""#1036 -- cliquet OFFLINE de la tranche `CabalOfSorcerers` (1496) / `GuardianConstruct` (1530).

Le test LIVE jumeau (`tests/engine/runner/test_1036_mythiques_owner_effect_live.py`) mesure la POSE
NATIVE ; mesure faite sur le jumeau #1025, il passerait encore SANS l'entree de registre, puisque
l'effet lui arrive aussi par la CAPTURE. C'est donc ICI que l'entree est gardee, et ici que se
tient le cran qui empeche la seule vraie regression possible sur cette tranche : inscrire un des
deux effets a `EFFECT_CLASSES` alors que le canal de RARETE n'existe toujours pas.

CINQ ETAGES :
  1. les deux abilities sont dans `ABILITY_INIT_OWNER_EFFECTS`, appariees a l'effet LU au decompile ;
  2. le REFUS d'`EFFECT_CLASSES` est CONDITIONNEL, pas fige : il ne mord que TANT QUE le port n'a
     pas de canal de rarete. Le jour ou le canal existe, cet etage se tait de lui-meme ;
  3. le mirror `idun.meta.Rarity` porte les ordinaux MESURES a la conversion (`probe_313` compare
     le mirror au BUILD : il redevient vert apres un renumerotage, alors que l'ordinal ECRIT au
     site, lui, a change -- cf. CLAUDE.md) ;
  4. l'appariement du mirror est celui que le COMBAT declare, LU dans `frida/methods.tsv`, et
     l'etage ASSERTIONNE SON PROPRE NON-VIDE (un balayage qui ne trouverait aucun foyer passerait
     pour vert) ;
  5. les enums HOMONYMES existent bel et bien : c'est ce qui rend l'etage 4 necessaire, et un
     ensemble vide y serait un faux vert.

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
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/probe_313_enum_mirror_bijection.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Etages 4 et 5 lisent `data/symbols/<build>/frida/{methods,enums}.tsv` -- un "
              "changement de build les concerne.",
}

#: L'appariement ability -> effet, LU au decompile (jamais deduit du nom) :
#:   `GuardianConstructAbility$$GetEffectType`  -> corps ENTIER `return 0x60c` = 1548 ;
#:   `CabalOfSorcerersAbility$$CreateBehaviour` -> `AddEffect(0x5d6 = 1494, ...)` au call-site.
ATTENDU = {
    "GuardianConstruct": ("GuardianConstruct_ExtraDamagePct", 1548),
    "CabalOfSorcerers": ("CabalOfSorcerers_ExtraDamagePct", 1494),
}

#: Les trois foyers de COMBAT dont le TYPE DECLARE du parametre `rarity` designe l'enum a mirrorer.
#: `case-1024` §4 nommait `IdunMetaLogic.UserProgress.Model.UnitRarity` : cet enum existe, mais ce
#: n'est PAS celui-ci -- et comme les deux ont les memes ordinaux, la faute serait SILENCIEUSE.
FOYERS_RARETE = (
    "IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity",
    "IdunBattleLogic.Entities.DSLTriggers.HasRarity",
    "IdunBattle.Entities.UnitExtensions.HasRarity",
)
CLE_RARETE_ATTENDUE = "idun.meta.Rarity"


def _canal_rarete_existe() -> bool:
    """Le port a-t-il, pour une UNITE, un canal de rarete ? DERIVE, jamais enumere : on regarde le
    porteur de contexte d'unite lui-meme. Tant que c'est faux, tout gate `HasRarity` /
    `UnitsWithRarity` est inevaluable et un effet qui en depend ne peut pas entrer au registre."""
    from engine.entities.unit_context import UnitContext
    return "rarity" in getattr(UnitContext, "__annotations__", {})


# ============================================ (1) les deux abilities posent leur owner-effect

@pytest.mark.parametrize("ability", sorted(ATTENDU))
def test_ability_init_owner_effect_inscrite(ability):
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS

    nom_effet, ordinal = ATTENDU[ability]
    assert ability in ABILITY_INIT_OWNER_EFFECTS, (
        f"{ability} n'est plus dans ABILITY_INIT_OWNER_EFFECTS : l'owner-effect permanent pose a "
        f"l'init (`AddEffect(GetEffectType(), targets = Owner)`) n'est plus seede offline")
    assert ABILITY_INIT_OWNER_EFFECTS[ability] == [nom_effet], (
        f"{ability} -> {ABILITY_INIT_OWNER_EFFECTS[ability]} ; l'appariement LU au decompile est "
        f"[{nom_effet!r}]")
    # L'ordinal est FIGE ici parce qu'il est ECRIT au site du decompile cite (0x60c / 0x5d6).
    assert int(getattr(EffectType, nom_effet)) == ordinal, (
        f"EffectType.{nom_effet} = {int(getattr(EffectType, nom_effet))} ; le decompile dit "
        f"{ordinal}")


# ====================== (2) le refus d'EFFECT_CLASSES est CONDITIONNEL au canal de rarete

@pytest.mark.parametrize("ability", sorted(ATTENDU))
def test_effet_au_registre_avec_son_gate_de_rarete(ability):
    """Les DEUX `$$CreateTargetSelector` finissent par `UnitsWithRarity(..., Rarity.Mythic = 5)`.

    L'inscrire sans le gate serait un terme PERMISSIF -- et INVISIBLE en test, puisque `rl_duel
    build` impose `targetRarity = 5` a toute unite normalisee : le gate y est uniformement VRAI
    (regime DEGENERE).

    ⚠ CE CRAN A ROUGI DEUX FOIS, ET IL A EU RAISON LES DEUX FOIS.
      1. (#999-r3) le canal de rarete est apparu (`UnitContext.rarity`, `HasRarity`,
         `UnitsWithRarity`, confrontes live en regime SEPARANT) : sa premiere raison d'etre --
         << la rarete est inevaluable >> -- a disparu, et il l'a dit au lieu de se taire ;
      2. (#1036-r1/-r2) les deux effets sont entres a `EFFECT_CLASSES` : il a force la relecture,
         et il est REQUALIFIE ici -- il n'assertionne plus l'ABSENCE, il assertionne la PRESENCE
         **avec** le gate. Un cran qui ne peut que descendre est un cran qui perd son objet en
         silence ; celui-ci rougit desormais si le canal part, si l'effet sort du registre, ou si
         son gate de rarete cesse de mordre (etage 6, couples accorde/refuse)."""
    from engine.entities.effects.factory import EFFECT_CLASSES

    nom_effet, _ = ATTENDU[ability]
    assert _canal_rarete_existe(), (
        "`UnitContext.rarity` a DISPARU : le canal de rarete (#999-r3) est retire et les deux "
        "effets redeviennent inevaluables pour la RAISON D'ORIGINE. Relire "
        "`docs/rl/case-999r3-canal-rarete.md`.")
    assert nom_effet in EFFECT_CLASSES, (
        f"{nom_effet} est SORTI d'EFFECT_CLASSES : l'effet redevient un `BaseEffect` NU -- present "
        f"dans la liste et sans aucun canal de degat. Le port vit dans "
        f"`engine/entities/effects/loki/extra_damage_aura.py` (#1036-r1/-r2).")


# ============================================ (3) les ordinaux du mirror, figes AU SITE

def test_mirror_rarity_ordinaux_figes():
    from engine.entities.rarity import Rarity

    assert {m.name: int(m) for m in Rarity} == {
        "Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3, "Legendary": 4, "Mythic": 5}
    # C'est `Mythic` que les deux selecteurs de la tranche exigent, et `5` est l'ordinal ECRIT.
    assert int(Rarity.Mythic) == 5


# ================= (4) l'appariement du mirror est celui que le COMBAT declare (methods.tsv)

def test_le_combat_declare_bien_idun_meta_rarity():
    from symbols_layout import build_dir, current_build

    p = Path(build_dir(current_build())) / "frida" / "methods.tsv"
    if not p.exists():
        pytest.skip(f"table absente : {p}")
    vus: dict[str, str] = {}
    for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
        col = ligne.split("\t")
        if len(col) < 6 or col[1] not in FOYERS_RARETE:
            continue
        for param in col[5].split(","):
            nom, _, typ = param.partition(":")
            if nom.strip() == "rarity":
                vus[col[1]] = typ.strip()
    # ASSERTIONNER SON PROPRE NON-VIDE : un balayage qui ne trouve rien passerait pour vert.
    assert set(vus) == set(FOYERS_RARETE), (
        f"foyers de rarete introuvables dans {p.name} : trouves={sorted(vus)} "
        f"attendus={sorted(FOYERS_RARETE)}")
    assert set(vus.values()) == {CLE_RARETE_ATTENDUE}, (
        f"le type declare du parametre `rarity` n'est plus unique/attendu : {vus}")


# ================= (5) les homonymes existent -- c'est ce qui rend l'etage 4 necessaire

def test_les_enums_de_rarete_homonymes_existent_et_partagent_les_ordinaux():
    from symbols_layout import build_dir, current_build

    p = Path(build_dir(current_build())) / "frida" / "enums.tsv"
    if not p.exists():
        pytest.skip(f"table absente : {p}")
    familles: dict[str, str] = {}
    for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ligne.startswith("#!"):
            continue
        col = ligne.split("\t")
        if len(col) < 2 or not col[0].split(".")[-1].endswith("Rarity"):
            continue
        familles[col[0]] = col[1]
    assert CLE_RARETE_ATTENDUE in familles, (
        f"{CLE_RARETE_ATTENDUE} absent de enums.tsv : {sorted(familles)}")
    autres = sorted(set(familles) - {CLE_RARETE_ATTENDUE})
    # NON-VIDE assertionne : s'il n'y avait PAS d'homonyme, l'etage 4 serait sans objet -- et cet
    # etage-ci passerait vert en ne montrant rien.
    assert autres, "aucun enum de rarete homonyme : l'etage 4 n'aurait plus de raison d'etre"
    memes = [n for n in autres if familles[n] == familles[CLE_RARETE_ATTENDUE]]
    assert memes, (
        f"aucun homonyme ne partage les ordinaux d'{CLE_RARETE_ATTENDUE} -- la confusion ne serait "
        f"plus silencieuse, et la raison ecrite dans `engine/entities/rarity.py` serait a revoir")


# ============ (6) chaque conjoint des DEUX arbres, garde par un COUPLE accorde / refuse

def _effet(nom, ordinal, *, level=1, mult=100, source=87):
    from engine.entities.effects.factory import EffectFactory
    return EffectFactory.create(
        {"name": nom, "effectType": ordinal, "level": level, "source": source}, mult, level, None)


def _ctx_guardian():
    """Le ctx MINIMAL qui accorde le bonus de `GuardianConstruct_ExtraDamagePct` (1548)."""
    from engine.entities.effects.loki.extra_damage_aura import CTX_ATT_EFFECT_NAMES
    from engine.entities.effect_type import EffectType
    from engine.entities.rarity import Rarity
    return {
        "owner_id": 87, "owner_team": 0, "att_id": 5, "att_team": 0,
        "att_rarity": Rarity.Mythic,                        # UnitsWithRarity(..., Mythic)
        CTX_ATT_EFFECT_NAMES: frozenset([EffectType.NanoscarabRepairProtocols.name]),
    }


def _ctx_cabal():
    """Le ctx MINIMAL qui accorde le bonus de `CabalOfSorcerers_ExtraDamagePct` (1494), branche
    `F` (porteur MACHINE, l'attaquant a un allie qualifie adjacent)."""
    from engine.entities.effects.loki.extra_damage_aura import (
        CTX_OWNER_IS_MACHINE, CTX_CABAL_VALID_ADJACENT_TO_ATT)
    from engine.entities.damage_profile_type import DamageProfileType
    from engine.entities.rarity import Rarity
    from engine.entities.traits.unit_trait import UnitTrait
    return {
        "owner_id": 87, "owner_team": 0, "att_id": 5, "att_team": 0,
        "att_rarity": Rarity.Mythic,
        "att_traits": frozenset([UnitTrait.Psyker.name, UnitTrait.Hero.name]),
        "damage_profile": DamageProfileType.Psychic.name,
        CTX_OWNER_IS_MACHINE: {87: True},
        CTX_CABAL_VALID_ADJACENT_TO_ATT: 1,
    }


#: (libelle, mutation du ctx qui doit FAIRE TAIRE le gate). Un a un : chaque conjoint LU au
#: decompile a son couple, sinon un terme peut disparaitre du port sans qu'aucun test ne bouge.
_REFUS_GUARDIAN = (
    ("rarete NON Mythic (UnitsWithRarity)", lambda c, R: c.update(att_rarity=R.Epic)),
    ("rarete NON MESUREE -> gate FERME", lambda c, R: c.update(att_rarity=None)),
    ("attaquant SANS NanoscarabRepairProtocols", lambda c, R: c.update(att_effect_names=frozenset())),
    ("canal d'effets NON MESURE -> FERME", lambda c, R: c.update(att_effect_names=None)),
    ("attaquant d'une AUTRE equipe (Friends)", lambda c, R: c.update(att_team=1)),
    ("equipe du porteur NON MESUREE", lambda c, R: c.update(owner_team=None)),
)

_REFUS_CABAL = (
    ("profil NON Psychic (CurrentAttackDamageProfileIs)",
     lambda c, R: c.update(damage_profile="Physical")),
    ("profil NON MESURE -> gate FERME", lambda c, R: c.update(damage_profile=None)),
    ("rarete NON Mythic (ValidCharacter)", lambda c, R: c.update(att_rarity=R.Epic)),
    ("rarete NON MESUREE -> gate FERME", lambda c, R: c.update(att_rarity=None)),
    ("traits SANS Hero (op_BitwiseAnd = INTERSECTION)",
     lambda c, R: c.update(att_traits=frozenset(["Psyker"]))),
    ("traits SANS Psyker (op_BitwiseAnd = INTERSECTION)",
     lambda c, R: c.update(att_traits=frozenset(["Hero"]))),
    ("traits NON MESURES -> gate FERME", lambda c, R: c.update(att_traits=None)),
    ("attaquant d'une AUTRE equipe (Friends)", lambda c, R: c.update(att_team=1)),
    ("aucun allie qualifie ADJACENT (filtre F)",
     lambda c, R: c.update(cabal_valid_adjacent_to_attacker=0)),
    ("voisinage NON MESURE -> gate FERME",
     lambda c, R: c.update(cabal_valid_adjacent_to_attacker=None)),
)


@pytest.mark.parametrize("libelle,mutation", _REFUS_GUARDIAN, ids=[t[0] for t in _REFUS_GUARDIAN])
def test_guardian_construct_chaque_conjoint_refuse(libelle, mutation):
    from engine.entities.rarity import Rarity

    e = _effet(*ATTENDU["GuardianConstruct"])
    accorde = e.create_aura_attack_damage_bonus_for_ally(_ctx_guardian())
    assert accorde is not None and accorde.kind == "PercentIncrease", (
        f"le ctx ACCORDANT ne rend plus de bonus ({accorde!r}) : le couple accorde/refuse n'a plus "
        f"de temoin non nul, et tous les refus ci-dessous passeraient pour verts")
    c = _ctx_guardian()
    mutation(c, Rarity)
    assert e.create_aura_attack_damage_bonus_for_ally(c) is None, (
        f"le conjoint << {libelle} >> ne mord PLUS : le port est devenu PERMISSIF sur ce terme")


@pytest.mark.parametrize("libelle,mutation", _REFUS_CABAL, ids=[t[0] for t in _REFUS_CABAL])
def test_cabal_of_sorcerers_chaque_conjoint_refuse(libelle, mutation):
    from engine.entities.rarity import Rarity

    e = _effet(*ATTENDU["CabalOfSorcerers"])
    accorde = e.create_aura_attack_damage_bonus_for_ally(_ctx_cabal())
    assert accorde is not None and accorde.kind == "PercentIncrease", (
        f"le ctx ACCORDANT ne rend plus de bonus ({accorde!r}) : le couple accorde/refuse n'a plus "
        f"de temoin non nul, et tous les refus ci-dessous passeraient pour verts")
    c = _ctx_cabal()
    mutation(c, Rarity)
    assert e.create_aura_attack_damage_bonus_for_ally(c) is None, (
        f"le conjoint << {libelle} >> ne mord PLUS : le port est devenu PERMISSIF sur ce terme")


def test_cabal_branche_ifFalse_seulement_sur_un_porteur_NON_machine():
    """`ConditionalSelector(IsMachine(Owner), ifTrue = F, ifFalse = Unique(A + F))`.

    `A = ValidCharacter(AdjacentFriends(Owner))` n'entre QUE si le porteur n'est PAS une machine.
    Le meme ctx, a `owner_is_machine` pres, doit donc changer de verdict -- et le TRI-ETAT
    (`None` = non mesure) doit se comporter comme la branche `ifTrue`, jamais ouvrir `ifFalse`."""
    from engine.entities.effects.loki.extra_damage_aura import (
        CTX_OWNER_IS_MACHINE, CTX_CABAL_VALID_ADJACENT_TO_ATT)

    e = _effet(*ATTENDU["CabalOfSorcerers"])
    base = _ctx_cabal()
    base[CTX_CABAL_VALID_ADJACENT_TO_ATT] = 0        # F ne retient PAS l'attaquant
    base["owner_pos"], base["att_pos"] = (3, 3), (3, 4)   # ... mais il est ADJACENT au porteur

    machine = dict(base, **{CTX_OWNER_IS_MACHINE: {87: True}})
    assert e.create_aura_attack_damage_bonus_for_ally(machine) is None, (
        "porteur MACHINE : seule la branche `F` s'applique, l'adjacence au porteur ne doit RIEN "
        "accorder")
    non_machine = dict(base, **{CTX_OWNER_IS_MACHINE: {87: False}})
    assert e.create_aura_attack_damage_bonus_for_ally(non_machine) is not None, (
        "porteur NON machine : la branche `ifFalse` ajoute `A = ValidCharacter(AdjacentFriends("
        "Owner))`, donc l'attaquant qualifie ADJACENT au porteur doit etre accorde")
    non_mesure = dict(base, **{CTX_OWNER_IS_MACHINE: {}})
    assert e.create_aura_attack_damage_bonus_for_ally(non_mesure) is None, (
        "nature d'entite NON MESUREE : le port ne doit PAS deviner `False` -- ce serait ouvrir la "
        "branche `ifFalse` sur une affirmation que personne n'a mesuree")


def test_les_deux_faces_lisent_les_MEMES_cles_de_ctx():
    """Pas de fork PREDICTION / COMBAT : les trois cles neuves sont posees par les DEUX foyers, et
    par le MEME nom -- importe depuis le module d'effet, jamais recopie en litteral."""
    import re

    from engine.entities.effects.loki import extra_damage_aura as A

    cles = (A.CTX_ATT_EFFECT_NAMES, A.CTX_OWNER_IS_MACHINE, A.CTX_CABAL_VALID_ADJACENT_TO_ATT)
    foyers = ("engine/runner/damage_model.py", "engine/playbook/prediction/_shared.py")
    for foyer in foyers:
        src = (PYDIR / foyer).read_text(encoding="utf-8", errors="replace")
        # Le foyer doit IMPORTER les constantes (pas recopier les chaines) ...
        assert re.search(r"from .*extra_damage_aura import", src), (
            f"{foyer} n'importe pas les cles de ctx depuis `extra_damage_aura` : un litteral "
            f"recopie diverge en silence")
        for cle in cles:
            assert f'"{cle}"' not in src, (
                f"{foyer} recopie le litteral {cle!r} au lieu d'importer la constante")
    # ... et le module d'effet est le SEUL a les definir.
    src_effet = (PYDIR / "engine/entities/effects/loki/extra_damage_aura.py").read_text(
        encoding="utf-8", errors="replace")
    for cle in cles:
        assert f'= "{cle}"' in src_effet, f"{cle} n'est plus definie dans le module d'effet"
