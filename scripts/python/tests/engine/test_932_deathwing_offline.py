"""#932 -- les VERDICTS du passif `Deathwing` (`darkaTerminator` << Baraqiel >>), graves contre les
TABLES VERSIONNEES du build, pas contre une lecture de ce jour.

Sept etages, tous OFFLINE (aucun runner, aucun RPC) :

  1. FACES DEAD    -- `CalculateAttackUtilityInSteps` / `CalculateRepairUtilityInSteps` heritees de
                      `TriggeredAbilityPlaybook<T>`, corps `yield return Fix64.op_Implicit(0)`.
  2. FACE NON-OWNER ABSENTE -- aucune `DeathwingNonOwnerPlaybook` dans `frida/classes.tsv`, aucune
                      cle `DEATHWING*` dans `Utilities.Default.TriggeredAbilitiesNonOwner`.
  3. PARENTE       -- `DeathwingPlaybook -> AdjacentUnitPreferenceTriggeredAbilityPlaybook`1` et
                      `DeathwingEffect -> BaseEffect` (le PIEGE d'homonymie : le pseudo-C du `.ctor`
                      de l'effet designe un corps ICF-fondu partage avec `HealBlockingEffect`).
  4. ORDINAUX      -- les huit litteraux ECRITS AUX SITES, figes contre `frida/enums.tsv`.
  5. DOUBLEMENT    -- les quatre regimes de `GetDoubleEffectCondition` + le tri-etat des cles.
  6. GATE DE NATURE-- `IsMeleeAttack | NOT IsNormalAttack` sur la face ATTAQUE, ABSENT sur la face
                      DEFENSE.
  7. REGISTRES     -- les trois inscriptions (playbook MOVE, `EFFECT_CLASSES`, `ABILITY_TRIGGERS`)
                      et la cle BC, LUE au slot de string literal.

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le port lui-meme : la classe d'effet (les deux faces + le predicat de doublement) et le
        # trigger d'accumulation.
        "scripts/python/engine/entities/effects/loki/deathwing.py",
        "scripts/python/engine/runner/operations/triggers/loki/deathwing.py",
        # Les TROIS registres dont l'etage 7 exige la coexistence.
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        # Les mirrors d'enum dont l'etage 4 FIGE les ordinaux ECRITS AUX SITES.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        # Le canal de degat dont l'etage 6 lit le KIND (Addition / Subtraction) et le porteur.
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/entities/effects/base.py",
        # Le confront LIVE dont ces gardes figent le resultat.
        "scripts/python/probe_932_deathwing.py",
        # L'etage 1bis LIT le `global-metadata.dat` du build INSTALLE : il passe par le pin de build
        # et par le lecteur de metadata, dont un changement le rendrait muet (ou faux).
        "scripts/python/build_pin.py",
        "scripts/python/il2cpp_metadata.py",
        "scripts/python/il2cpp_provenance.py",
        # La seed BC, LUE a l'execution : c'est une ENTREE versionnee (`data/` = ce qu'on LIT), donc
        # son contenu peut changer le verdict. Son absence rendait ce fichier `DECLARE TROP ETROIT`
        # -- et un declencheur trop etroit est un FAUX VERT (#486-r15) : le fichier ne se rejoue pas
        # quand ce qu'il garde a bouge.
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Ces gardes figent des VERDICTS DE LECTURE que rien d'autre ne tient : les faces ATTACK / "
        "REPAIR sont DEAD (corps herite `yield Fix64(0)`), la face NON-OWNER n'existe pas, et la "
        "parente de `DeathwingEffect` est `BaseEffect` -- alors que le pseudo-C de son `.ctor` "
        "designe un corps ICF-fondu partage avec `HealBlockingEffect`. Aucun test de comportement "
        "ne peut rougir sur ces trois-la : ils portent sur ce que le binaire N'A PAS. "
        "`build: True` : les etages 1 a 4 lisent `frida/methods.tsv`, `frida/classes.tsv`, "
        "`frida/enums.tsv`, `ghidra/functions.tsv` et `metadata/string_literals.tsv` du hash "
        "COURANT -- un renumerotage, un symbole neuf sur une face heritee ou une classe non-owner "
        "ajoutee au prochain build les rendent faux, et c'est precisement ce que ce fichier doit "
        "voir."
    ),
}

import io          # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import json        # noqa: E402
from pathlib import Path                                               # noqa: E402

import pytest                                                          # noqa: E402

#: `.../scripts/python/tests/engine/<ce fichier>` -> quatre crans jusqu'a la RACINE du depot.
ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
BUILD = (DATA / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
SYM = DATA / "symbols" / BUILD

METHODS_TSV = SYM / "frida" / "methods.tsv"
CLASSES_TSV = SYM / "frida" / "classes.tsv"
ENUMS_TSV = SYM / "frida" / "enums.tsv"
GHIDRA_TSV = SYM / "ghidra" / "functions.tsv"
LITERALS_TSV = SYM / "metadata" / "string_literals.tsv"
SEED_BC = DATA / "seed-bc.json"

#: la CLE `BC.Utilities` du poids de mouvement, LUE au slot de string literal `0x33fa868`
#: (`metadata/string_literals.tsv`), jamais devinee par prefixe -- lecon `SPIRITUALLDEADER_` (#212).
BC_KEY = "DEATHWING_AdjacentDAFriend"


def _lines(path: Path) -> list[str]:
    # PAS de `skip` : ces tables sont VERSIONNEES (`data/` = ce qu'on LIT). Leur absence est une
    # vraie faute -- un skip la rendrait invisible, exactement le vice que le garde #455 punit.
    assert path.exists(), f"table VERSIONNEE absente : {path}"
    return [l.rstrip("\n") for l in io.open(path, encoding="utf-8")]


def _methods_of(klass: str) -> list[str]:
    """Les methodes que `frida/methods.tsv` attribue a `klass` (colonne 3 = classe proprietaire)."""
    out = []
    for l in _lines(METHODS_TSV):
        c = l.split("\t")
        if len(c) > 2 and c[2] == klass:
            out.append(c[1].split(".")[-1])
    return out


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- les faces ATTACK / REPAIR sont DEAD (heritees, corps `yield Fix64(0)`)
# ---------------------------------------------------------------------------------------------

def test_e1_faces_attack_et_repair_sont_dead():
    """`DeathwingPlaybook` n'a QUE deux entrees dans `frida/methods.tsv` (`.ctor` et
    `GetAdjacentFriendUtility`) : ni `CalculateAttackUtilityInSteps*` ni
    `CalculateRepairUtilityInSteps*`. Ces deux faces viennent donc de la base
    `TriggeredAbilityPlaybook<T>`, dont les corps (PRESENTS dans `ghidra/functions.tsv` -- un
    generique pleinement partage est absent du dump FRIDA, present dans le dump GHIDRA) sont des
    iterateurs `yield return Fix64.op_Implicit(0)`.

    ⚠ CE QUE CE TEST NE PROUVE PAS : l'absence dans `methods.tsv` ne prouve rien a elle seule
    (l'ICF fond les corps triviaux, un corps partage n'a qu'UN proprietaire). Le verdict DEAD est
    etabli par le `global-metadata.dat` (etage 1bis, la source COMPLETE) ; CE test est le CLIQUET :
    il rougira le jour ou un build DONNE un symbole propre a l'une des deux faces sur cette classe,
    c'est-a-dire exactement quand elles cesseront d'etre heritees."""
    ms = _methods_of("IdunBattle.AI.Playbook.Loki.DeathwingPlaybook")
    assert ms, "aucune methode attribuee a DeathwingPlaybook -- table vide ou renommee"
    # `..ctor` -> `split('.')[-1]` rend `ctor` : le point de tete appartient au SEPARATEUR.
    assert sorted(ms) == sorted(["ctor", "GetAdjacentFriendUtility"]), \
        f"methodes de DeathwingPlaybook dans methods.tsv : {sorted(ms)}"
    assert not [m for m in ms if m.startswith("Calculate")], \
        "une face Calculate*UtilityInSteps a recu un symbole propre -> elle n'est plus heritee"
    # les DEUX corps de la base existent bien (sinon le verdict << herite >> serait vide de sens)
    g = "\n".join(_lines(GHIDRA_TSV))
    for face in ("CalculateAttackUtilityInStepsInternal", "CalculateRepairUtilityInStepsInternal"):
        assert f"TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$${face}" in g, \
            f"corps de base introuvable pour {face}"
    # et leurs ITERATEURS -- c'est le `MoveNext` qui porte le `yield Fix64(0)`
    assert "u003CCalculateAttackUtilityInStepsInternalu003Ed__37" in g
    assert "u003CCalculateRepairUtilityInStepsInternalu003Ed__39" in g


def test_e1bis_metadata_ne_declare_que_les_deux_accesseurs():
    """SOURCE COMPLETE (`global-metadata.dat`) : `DeathwingPlaybook` ne DECLARE que
    `[.ctor, GetAdjacentFriendUtility (slot 13), GetAdjacentEnemyUtility (slot 14)]` -- ni cap
    (`GetMaxAdjacentFriendsToCount`), ni filtre (`FilterAdjacentFriends`), ni aucune face
    `Calculate*`. C'est CE constat, et non l'absence de symbole, qui etablit le verdict DEAD.

    SKIP si le jeu n'est pas installe (le `global-metadata.dat` vit hors du depot) -- l'etage 1
    ci-dessus reste, lui, jouable partout."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "python"))
    try:
        import build_pin
        dll = build_pin.game_dll()
    except Exception as exc:                                   # jeu absent / build desaligne
        pytest.skip(f"global-metadata.dat non lisible : {type(exc).__name__}: {exc}")
    meta = next(iter(dll.parent.rglob("global-metadata.dat")), None)
    if meta is None:
        pytest.skip("global-metadata.dat introuvable a cote de GameAssembly.dll")
    import il2cpp_metadata as MD
    ancres = (("Core.Services", "OperationProcessor"),
              ("IdunBattle.Core.Services", "BattleQuery"),
              ("IdunBattle.Core.Services", "AttackQuery"),
              ("IdunBattle.Core.Services", "MovementQuery"),
              ("IdunBattle.Core.Services", "DamageCalculations"),
              ("IdunBattle.Core", "MatchState"))
    # MONTAGE DE LA GRILLE MIS EN CACHE PAR LE BUILD (#1029) : c'est lui qui coutait 19,2 s, pas la
    # lecture des deux types. `noms_declares` rend `None` si la mesure est impossible -- on SKIP
    # alors, comme avant, au lieu de conclure.
    types = (("IdunBattle.AI.Playbook.Loki", "DeathwingPlaybook"),
             ("IdunBattle.Entities.Effects.Loki", "DeathwingEffect"))
    table = MD.noms_declares(meta, METHODS_TSV, ancres, types)
    if table is None:
        pytest.skip("metadata non alignable sur ce build -- derivation REFUSEE, rien devine")
    noms = table[("IdunBattle.AI.Playbook.Loki", "DeathwingPlaybook")]
    assert sorted(noms) == sorted([".ctor", "GetAdjacentFriendUtility", "GetAdjacentEnemyUtility"]), \
        f"declarations de DeathwingPlaybook : {sorted(noms)}"
    eff = table[("IdunBattle.Entities.Effects.Loki", "DeathwingEffect")]
    assert sorted(eff) == sorted([".ctor", "CreateActiveCondition", "CreateTargetSelector",
                                  "CreateEffectDamageBonusForAttack",
                                  "CreateEffectDamageMalusForDefense",
                                  "GetEffectAmount", "GetDoubleEffectCondition"]), \
        f"declarations de DeathwingEffect : {sorted(eff)}"


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- la face NON-OWNER n'existe PAS pour ce passif
# ---------------------------------------------------------------------------------------------

def test_e2_pas_de_face_non_owner():
    """Deux sources INDEPENDANTES, et il en faut deux : la classe et la table de poids.

    (a) `frida/classes.tsv` ne porte AUCUNE `Deathwing*NonOwnerPlaybook` -- alors qu'il en porte
        28 pour d'autres abilities (temoin NON-VIDE assertionne : un ensemble vide ferait passer
        ce test pour vert sans rien mesurer) ;
    (b) `Utilities.Default.TriggeredAbilitiesNonOwner` (25 cles) ne porte aucune cle `DEATHWING*`.

    Consequence portee : rien a inscrire dans `playbook/non_owner.py`, et l'absence y vaut 0 --
    exactement ce que rend le natif quand `LoadPlaybookNonOwner` ne trouve rien."""
    classes = _lines(CLASSES_TSV)
    non_owner = [l.split("\t")[0] for l in classes if "NonOwnerPlaybook" in l.split("\t")[0]]
    assert len(non_owner) >= 20, f"temoin trop maigre : {len(non_owner)} NonOwnerPlaybook"
    assert not [c for c in non_owner if "Deathwing" in c], \
        f"une face NON-OWNER Deathwing est apparue : {[c for c in non_owner if 'Deathwing' in c]}"
    bc = json.load(io.open(SEED_BC, encoding="utf-8"))
    tan = bc["Utilities"]["Default"]["TriggeredAbilitiesNonOwner"]
    assert len(tan) >= 20, f"temoin trop maigre : {len(tan)} cles TriggeredAbilitiesNonOwner"
    assert not [k for k in tan if "DEATHWING" in k.upper()], \
        f"cle non-owner Deathwing apparue : {[k for k in tan if 'DEATHWING' in k.upper()]}"


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- PARENTE lue dans `classes.tsv` (le piege d'homonymie)
# ---------------------------------------------------------------------------------------------

def test_e3_parente_lue_dans_classes_tsv():
    """`DeathwingEffect` derive de `BaseEffect`, PAS de `HealBlockingEffect` -- et c'est la seule
    source qui tranche : le `.ctor` de l'effet partage son corps, par ICF, avec ceux de
    `FuryOfTheAncientsEffect` et `MischiefMakersEffect`, qui derivent, eux, de `HealBlockingEffect`.
    Suivre le pseudo-C donnerait un BLOCAGE DE SOIN la ou l'i2 annonce un effet de DEGAT.

    `DeathwingPlaybook` derive d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook`1`, PAS
    d'`AdjacentToOwnerNonOwnerPlaybook`1` que le pseudo-C de son `.ctor` designe (meme fold gshared,
    meme mislabel que `IconOfObstinacyPlaybook`)."""
    # `frida/classes.tsv` : `<nom plein>\t<taille>\t<parent>\t<flags>` -- le parent est la 3e cellule.
    parents = {}
    for l in _lines(CLASSES_TSV):
        c = l.split("\t")
        if len(c) > 2:
            parents[c[0]] = c[2]
    assert parents.get("IdunBattle.Entities.Effects.Loki.DeathwingEffect") == \
        "IdunBattle.Entities.Effects.BaseEffect"
    assert parents.get("IdunBattle.Entities.Effects.Loki.FuryOfTheAncientsEffect") == \
        "IdunBattle.Entities.Effects.HealBlockingEffect", \
        "le temoin du piege a disparu -- le contraste qui rend l'assertion ci-dessus signifiante"
    assert parents.get("IdunBattle.AI.Playbook.Loki.DeathwingPlaybook") == \
        "IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook`1"
    assert parents.get("IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingAbility") == \
        "IdunBattle.Entities.Abilities.BaseTriggeredAbility"
    # la fille n'override que `GetEffectType` -- c'est ce qui rend `DeathwingKnight` distincte
    assert parents.get("IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingKnightAbility") \
        == "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingAbility"


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- les ORDINAUX ECRITS AUX SITES, figes contre `frida/enums.tsv`
# ---------------------------------------------------------------------------------------------

def _enum(nom_plein: str) -> dict:
    for l in _lines(ENUMS_TSV):
        c = l.split("\t")
        if c and c[0] == nom_plein:
            out = {}
            for kv in c[1].split(","):
                k, v = kv.split("=")
                out[v] = int(k)
            return out
    raise AssertionError(f"enum introuvable dans enums.tsv : {nom_plein}")


def test_e4_ordinaux_figes():
    """`probe_313` compare le MIRROR au BUILD ; il redevient vert des qu'on regenere le mirror
    apres un renumerotage. Ce test-ci fige l'ordinal MESURE A LA CONVERSION, au SITE.

    ⚠ Les enums sont QUALIFIES : `EventTriggerType` 9 est `Attack` dans `IdunBattle.DSL`, mais
    `Select` dans `UnityEngine.EventSystems` ; `EffectType.Deathwing` (1318) et
    `TriggeredAbilityType.Deathwing` (1245) sont DEUX ids differents pour le MEME nom."""
    assert _enum("IdunBattle.DSL.EventTriggerType")["Attack"] == 9
    assert _enum("IdunBattle.Entities.Enum.UnitFaction")["DarkAngels"] == 10
    assert _enum("IdunBattle.Entities.Enum.UnitSelectionType")["OnlyAliveAndTargetable"] == 3
    assert _enum("IdunBattle.Entities.Enum.EffectTargetType")["Both"] == 6
    av = _enum("IdunBattle.Configuration.AbilityVariableType")
    assert av["extraDmg"] == 8 and av["dmgReduction"] == 0x12
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(EffectType.Deathwing) == 0x526 == 1318
    assert int(TriggeredAbilityType.Deathwing) == 0x4dd == 1245
    assert int(EffectType.DeathwingKnight) == 0x5e8 == 1512
    assert int(EffectType.Deathwing) != int(TriggeredAbilityType.Deathwing), \
        "meme NOM, deux enums -- les confondre lirait la mauvaise cle"
    # `UnitTrait` 0x7ea = grande-alliance Chaos, DERIVEE du `GrandAllianceId` (pas dans le kit)
    from engine.entities.effects.loki.deathwing import GRAND_ALLIANCE_CHAOS
    assert GRAND_ALLIANCE_CHAOS == "Chaos"
    ut = _enum("IdunBattle.Entities.Enum.UnitTrait")
    assert ut.get("Chaos") == 0x7ea


# ---------------------------------------------------------------------------------------------
# ETAGE 5 -- `GetDoubleEffectCondition` : quatre regimes + tri-etat
# ---------------------------------------------------------------------------------------------

def _eff(level=1, ablvl=50, mult=100):
    from engine.entities.effects.loki.deathwing import DeathwingEffect
    return DeathwingEffect(name="Deathwing", effect_type=1318, level=level,
                           ability_level=ablvl, ability_variables_multiplier=mult)


def _base_amount(var: str, ablvl=50, mult=100) -> int:
    from engine.entities.effects.magnitude import ability_var
    return int(ability_var("Deathwing", var, ablvl, multiplier_pct=mult))


def test_e5_doublement_les_quatre_regimes():
    """`( HasTrait(X, Chaos) & AreEnemies(X, Owner) ) | AmountIsGreaterThanZero(<amis DA adjacents>)`.

    Les quatre bras : ni l'un ni l'autre / Chaos seul / ami DA seul / les deux."""
    e = _eff(level=1)
    base = _base_amount("extraDmg")
    assert base > 0
    def bonus(alliance, adj, tgt_team=1, att_team=0):
        eb = e.create_effect_damage_bonus_for_attack(
            is_ranged=False, att_ctx={"tgt_grand_alliance": alliance, "tgt_team": tgt_team,
                                      "att_team": att_team, "adjacent_dark_angels_friends": adj})
        return eb.value if eb is not None else None
    assert bonus("Imperial", 0) == base                    # aucun disjoint
    assert bonus("Chaos", 0) == 2 * base                   # disjoint 1 (ennemi Chaos)
    assert bonus("Imperial", 1) == 2 * base                # disjoint 2 (un frere Dark Angel)
    assert bonus("Chaos", 2) == 2 * base                   # les deux -> DOUBLE, jamais quadruple
    # `AreEnemies` MORD : un ALLIE Chaos (meme equipe) ne double pas
    assert bonus("Chaos", 0, tgt_team=0, att_team=0) == base


def test_e5bis_tri_etat_des_cles_ferme_le_disjoint():
    """Cle ABSENTE => disjoint FERME (degradation RESTRICTIVE : on sous-estime, on n'invente jamais
    un doublement). Et un compteur `None` (porteur sans equipe ni tuile) n'est PAS un 0 : il ferme
    SON disjoint sans toucher a l'autre."""
    e = _eff(level=1)
    base = _base_amount("extraDmg")
    # ctx VIDE : les deux disjoints fermes
    eb = e.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx={})
    assert eb is not None and eb.value == base
    # compteur non mesure MAIS cible Chaos ennemie -> le PREMIER disjoint tient
    eb = e.create_effect_damage_bonus_for_attack(
        is_ranged=False, att_ctx={"tgt_grand_alliance": "Chaos", "tgt_team": 1, "att_team": 0,
                                  "adjacent_dark_angels_friends": None})
    assert eb is not None and eb.value == 2 * base
    # equipes non mesurees -> `AreEnemies` ferme, meme avec un Chaos en face
    eb = e.create_effect_damage_bonus_for_attack(
        is_ranged=False, att_ctx={"tgt_grand_alliance": "Chaos"})
    assert eb is not None and eb.value == base


def test_e5ter_le_niveau_est_un_facteur():
    """`Multiply(ConfigVar, EffectLevel(Effect))` : la magnitude est `V x niveau`, pas `V`.
    Niveau 0/absent -> INERTE (jamais une contribution au niveau 1 par defaut)."""
    base = _base_amount("extraDmg")
    for lvl in (1, 2, 5):
        eb = _eff(level=lvl).create_effect_damage_bonus_for_attack(
            is_ranged=False, att_ctx={"att_team": 0, "tgt_team": 1,
                                      "adjacent_dark_angels_friends": 0})
        assert eb.value == base * lvl, f"niveau {lvl}"
    assert _eff(level=0).create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx={}) is None
    assert _eff(level=None).create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx={}) is None
    # niveau d'ability inconnu -> inerte (ConfigVar sans AbilityState)
    assert _eff(level=3, ablvl=None).create_effect_damage_bonus_for_attack(
        is_ranged=False, att_ctx={}) is None


# ---------------------------------------------------------------------------------------------
# ETAGE 6 -- le gate de NATURE n'est PAS symetrique entre les deux faces
# ---------------------------------------------------------------------------------------------

def test_e6_gate_de_nature_face_attaque_seulement():
    """Face ATTAQUE : `IsMeleeAttack() | NOT IsNormalAttack()` -- une attaque NORMALE A DISTANCE
    n'en beneficie pas, une attaque d'ABILITY (donc `PlasmaCannon`, ranged) si.
    Face DEFENSE : AUCUN gate de nature ni de profil -- toutes les attaques recues sont reduites."""
    e = _eff(level=1)
    base_att, base_def = _base_amount("extraDmg"), _base_amount("dmgReduction")
    ctx_a = {"att_team": 0, "tgt_team": 1, "adjacent_dark_angels_friends": 0}
    # melee normale -> OUI
    assert e.create_effect_damage_bonus_for_attack(is_ranged=False, is_normal_attack=True,
                                                   att_ctx=ctx_a).value == base_att
    # ranged NORMALE -> NON
    assert e.create_effect_damage_bonus_for_attack(is_ranged=True, is_normal_attack=True,
                                                   att_ctx=ctx_a) is None
    # ranged ABILITY -> OUI (le << ou Plasma Cannon >> de l'i2, ecrit PLUS LARGE par le natif)
    assert e.create_effect_damage_bonus_for_attack(is_ranged=True, is_normal_attack=False,
                                                   att_ctx=ctx_a).value == base_att
    # nature INCONNUE -> aucune contribution
    assert e.create_effect_damage_bonus_for_attack(is_ranged=None, is_normal_attack=None,
                                                   att_ctx=ctx_a) is None
    # DEFENSE : les quatre natures rendent la MEME reduction
    ctx_d = {"team": 1, "owner_team": 0, "adjacent_dark_angels_friends": 0}
    for melee in (True, False, None):
        for prof in ("Power", "Psychic", None):
            eb = e.create_effect_damage_malus_for_defense(is_melee=melee, damage_profile=prof,
                                                          attacker_ctx=ctx_d)
            assert eb is not None and eb.value == base_def, f"melee={melee} prof={prof}"
            assert eb.kind == "Subtraction" and eb.owner_is_caster is False


def test_e6bis_canaux_lus_aux_offsets_de_effectbonus():
    """La face ATTAQUE ecrit `EffectBonus+0x10` (Addition), la face DEFENSE `+0x18` (Subtraction) --
    offsets releves dans `EffectBonus$$ForAddition` / `$$ForSubtraction`. Les deux corps natifs
    construisent la struct A LA MAIN (aucun appel de fabrique), donc c'est l'OFFSET qui tranche le
    canal, pas un nom."""
    e = _eff(level=1)
    a = e.create_effect_damage_bonus_for_attack(
        is_ranged=False, att_ctx={"att_team": 0, "tgt_team": 1,
                                  "adjacent_dark_angels_friends": 0})
    d = e.create_effect_damage_malus_for_defense(
        is_melee=True, attacker_ctx={"team": 1, "owner_team": 0,
                                     "adjacent_dark_angels_friends": 0})
    assert a.kind == "Addition" and a.owner_is_caster is True
    assert d.kind == "Subtraction" and d.owner_is_caster is False


# ---------------------------------------------------------------------------------------------
# ETAGE 7 -- les trois REGISTRES + la cle BC
# ---------------------------------------------------------------------------------------------

def test_e7_registres_et_cle_bc():
    """Les trois inscriptions doivent coexister : sans l'une, la mecanique se degrade EN SILENCE
    (playbook manquant = terme de mouvement a 0 ; `EFFECT_CLASSES` manquant = effet inerte ;
    `ABILITY_TRIGGERS` manquant = compteur mort)."""
    from engine.playbook.adjacent_unit_preference import (TRIGGERED_MOVE_PLAYBOOKS,
                                                          DeathwingPlaybook)
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.deathwing import DeathwingEffect
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.deathwing import DeathwingAbility

    pb = TRIGGERED_MOVE_PLAYBOOKS.get(int(TriggeredAbilityType.Deathwing))
    assert isinstance(pb, DeathwingPlaybook)
    assert pb.KEY == BC_KEY
    assert EFFECT_CLASSES.get("Deathwing") is DeathwingEffect
    assert DeathwingAbility in ABILITY_TRIGGERS.get("Deathwing", [])
    # la CLE est celle du binaire, lue au slot de string literal (jamais devinee par prefixe)
    assert any(f'"{BC_KEY}"' in l for l in _lines(LITERALS_TSV)), \
        f"{BC_KEY} absente des string literals du build"
    # et elle est SERVIE par la table de poids
    bc = json.load(io.open(SEED_BC, encoding="utf-8"))
    assert bc["Utilities"]["Default"]["TriggeredAbilities"].get(BC_KEY) is not None


def test_e7bis_le_gate_de_faction_du_playbook_mord():
    """`if (!UnitExtensions.HasFaction(friend, 0xa)) return 0;` -- le gate est DANS l'accesseur de
    poids, pas dans un `FilterAdjacentFriends` (le metadata dit que la classe n'en declare aucun)."""
    from engine.playbook.adjacent_unit_preference import DeathwingPlaybook

    class _Wt:
        def sub(self, section, key):
            assert section == "TriggeredAbilities" and key == BC_KEY
            return 10

    pb, wt = DeathwingPlaybook(), _Wt()
    assert pb.get_adjacent_friend_utility({"vis": "darkaAzrael"}, wt) == 10.0
    assert pb.get_adjacent_friend_utility({"vis": "ultraApothecary"}, wt) == 0.0
    # la face ENNEMIS est un override EXPLICITE `return 0` (bloc `methodPointers` : `<ret 0>`)
    assert pb.get_adjacent_enemy_utility({"vis": "darkaAzrael"}, wt) == 0.0
    # ni cap ni filtre declares
    assert pb.MAX_ADJACENT_FRIENDS is None and pb.MAX_ADJACENT_ENEMIES is None
