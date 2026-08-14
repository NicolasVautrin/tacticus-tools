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
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/entities/effect_type.py",
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
def test_effet_hors_registre_tant_que_la_rarete_est_inevaluable(ability):
    """Les DEUX `$$CreateTargetSelector` finissent par `UnitsWithRarity(..., Rarity.Mythic = 5)`.

    L'inscrire sans le gate serait un terme PERMISSIF -- et INVISIBLE en test, puisque `rl_duel
    build` impose `targetRarity = 5` a toute unite normalisee : le gate y est uniformement VRAI
    (regime DEGENERE).

    ⚠ CE CRAN ROUGIT DANS LES DEUX SENS, et le second sens est le plus utile -- il est CALQUE sur
    `test_1025_electrochaff_backups_offline.py::test_verrou_de_rarete_fige_avec_sa_raison`, qui
    garde le MEME verrou pour 1446/1449. Se TAIRE le jour ou le canal apparait laisserait
    `#1036-r1`/`#1036-r2` dormir sans que personne ne l'apprenne : la tranche qui ouvre le capteur
    n'a aucune raison de relire cette case-doc. Un cran qui ne peut que descendre est un cran qui
    perd son objet en silence."""
    from engine.entities.effects.factory import EFFECT_CLASSES

    nom_effet, _ = ATTENDU[ability]
    if _canal_rarete_existe():
        assert False, (
            f"`UnitContext` porte desormais une RARETE : le verrou qui tenait {nom_effet} hors "
            f"d'`EFFECT_CLASSES` est leve. RELIRE `docs/rl/case-1036-mythiques-cabale-et-construct.md` "
            f"§2 (la RE des deux effets y est complete) et porter #1036-r1 / #1036-r2 -- ou "
            f"requalifier ce cran si le canal ne repond pas a `UnitsWithRarity`.")
    assert nom_effet not in EFFECT_CLASSES, (
        f"{nom_effet} est entre dans EFFECT_CLASSES alors qu'`UnitContext` ne porte AUCUNE rarete "
        f"-- son `$$CreateTargetSelector` serait donc applique SANS son etage "
        f"`UnitsWithRarity(Mythic)`, soit un terme PERMISSIF silencieux (residus #1036-r1/-r2, "
        f"BLOCAGE capteur)")


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
