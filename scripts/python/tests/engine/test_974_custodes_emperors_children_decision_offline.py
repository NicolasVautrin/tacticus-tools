"""#974 -- faces DECISION du lot Custodes / Emperor's Children, gardees SANS runner.

CINQ abilities ont ete soumises ; le RE en a ramene DEUX a porter et TROIS a des verdicts, que ce
fichier VERROUILLE pour qu'un lecteur ne les re-porte pas en jumeau :

  * `1195 TalonsOfTheEmperor` -- PORTEE. Base `minDmg` SEUL **plus** un terme FLAT
    (`GetExtraDamage`), et profil CONDITIONNEL. Les deux ecarts avec le generique vont en sens
    OPPOSES (la moyenne SUR-evalue, l'oubli du flat SOUS-evalue) : aucune mesure scalaire ne
    pouvait les separer, seul le decompile les nomme.
  * `1198 EuphoricStrikes` -- PORTEE. `NonComparable` : utilite = PV COURANTS de la cible, VETO
    `WillNormalAttackKill` EN TETE de boucle.
  * `1184 MomentShackle` -- DEJA PORTEE (`playbook/bespoke.py`), invisible aux TROIS registres que
    l'audit interroge. RELUE : juste.
  * `1191 MartialInspiration` -- DEJA PORTEE (`_MAKE_DMG_INPUT_OVERRIDES`), invisible pour la meme
    raison. RELUE : juste.
  * `1196 LashOfTorment` -- SANS CONTENU PROPRE : son `MakeDamagePredictions` est le chemin
    GENERIQUE strict (`GetDamage` / `GetHits` / `GetDamageProfile` ->
    `GenerateMultiHitAttackPredictions`), deja couvert. Meme verdict que `LeadingTheCharge` (1204)
    dans #945.

Les pieges REELS que ce fichier garde :

  1. **La BASE se lit dans `classes.tsv`, jamais dans le nom du `.ctor`** : `EuphoricStrikes` est
     `NonComparablePlaybook`1`, alors que ghidra nomme son ctor `ComparablePlaybook<...>` -- et
     `AlphaWarriorPlaybook$$.ctor`, NonComparable averee, appelle le MEME corps.
  2. **Ni `1195` ni `1196` n'ont de `ShouldExecute`**, donc leur `.cctor` `Fix64(1)` n'a AUCUN
     lecteur : ils ne sont PAS de la famille « seuil statique » (`Fix64(10)`).
  3. **`GetHits` n'est PAS surcharge par 1195** : poser un `hits_override` serait inventer.
  4. **Le profil de 1195 est CONDITIONNEL**, donc il ne peut pas vivre dans
     `_PLAYBOOK_PROFILE_OVERRIDE`, qui ne porte que des constantes.
  5. **`1198` ne construit AUCUNE prediction d'ability** : sa trace vaut AU PLUS UN event, celui du
     gate -- contrairement a `KillMaimBurn`, qui porte le meme gate et en emet DEUX.

Aucune magnitude n'est ecrite en dur : `minDmg` / `extraDmg` / `damageProfile*` sont re-derives du
gameconfig. Seules la STRUCTURE et les lectures du decompile sont assertees.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe les DEUX faces decision -- le registre
    # `PLAYBOOKS` (donc tout `engine.playbook.noncomparable`), `playbook.prediction.abilities`
    # (les deux registres d'override), `playbook.bespoke`, et `active_ability` (les familles de
    # moyenne de #344/#350). Sa fermeture d'import couvre l'essentiel des deux faces.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    # `frida/hooks/data/ability-names.ts` est la table `id -> nom d'ability` que `GC.ability_name`
    # lit : les assertions d'ANCRAGE (`GC.ability_name(1195) == "TalonsOfTheEmperor"`) en dependent
    # DIRECTEMENT, et toute la fiche est indexee sur ces noms.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "frida/hooks/data/ability-names.ts"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire : les seuils sont ceux LUS au
    # decompile et les magnitudes viennent du gameconfig, re-derivees a chaque passage.
    "build": False,
    # offline pur, aucun runner, < 3 s.
    "toujours": True,
    "raison": "Gardes OFFLINE des faces DECISION du lot Custodes / Emperor's Children (#974) : la "
              "base minDmg+flat et le profil CONDITIONNEL de 1195, le VETO WillNormalAttackKill et "
              "l'utilite PV de 1198, et les TROIS verdicts verrouilles (1184 et 1191 deja portees, "
              "1196 sans contenu propre).",
}

import pytest

import gameconfig as GC
import engine.playbook.prediction.abilities as PA

from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.entities.abilities.active_ability import (
    active_ability_for, makes_damage_predictions,
    _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE, _PREDICTION_MINMAX_RANDOM_READ)
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.unit_context import UnitContext
from engine.playbook.noncomparable import PLAYBOOKS
from engine.playbook.noncomparable._base import NCContext, _PlanTargetPlaybook

TALONS = int(ActiveAbilityType.TalonsOfTheEmperor)     # 0x4a3 = 1195
EUPHORIC = int(ActiveAbilityType.EuphoricStrikes)      # 0x4ae = 1198
MOMENT = int(ActiveAbilityType.MomentShackle)          # 0x4a0 = 1184
MARTIAL = int(ActiveAbilityType.MartialInspiration)    # 0x4a7 = 1191
LASH = int(ActiveAbilityType.LashOfTorment)            # 0x4ac = 1196


def _ability(name, aid, level):
    cfg = AbilityConfiguration.from_gameconfig(name, GC.ability(name))
    assert cfg is not None, "config gameconfig de %s introuvable" % name
    ab = active_ability_for(name, aid, UnitContext(entity_id=1), cfg,
                            ability_state={"level": level, "multiplier": 100})
    return ab, cfg


class _SceneStub:
    """Substrat MINIMAL du handler d'entrees : seuls `eff_state.by_unit`, `units`, `pos` et `board`
    sont consultes. Aucun runner, aucune capture."""

    def __init__(self, effects=None, units=None, board=None):
        self.eff_state = type("_ES", (), {"by_unit": effects or {}})()
        self.units = units or []
        self.board = board
        self.elev_by_pos = None

    def pos(self, _uid):
        return (0, 0)


class _EffStub:
    def __init__(self, effect_type, level, consumed=False):
        self.effect_type, self.level, self.consumed = effect_type, level, consumed


# =============================================================================================
# ETAGE 1 -- 1195 : LA BASE EST `minDmg` + UN TERME FLAT, JAMAIS LA MOYENNE
# =============================================================================================
def test_talons_est_au_registre_des_entrees_et_a_la_table_des_bases_non_moyennes():
    """Sans l'entree de registre, le handler n'est jamais appele : ni erreur, ni test rouge --
    exactement le no-op silencieux que #350 avait deja paye."""
    assert GC.ability_name(TALONS) == "TalonsOfTheEmperor", (
        "l'id %d ne resout plus a TalonsOfTheEmperor -- toute la fiche est indexee dessus" % TALONS)
    assert TALONS in PA._MAKE_DMG_INPUT_OVERRIDES
    assert PA._MAKE_DMG_INPUT_OVERRIDES[TALONS] is PA._talons_of_the_emperor_inputs
    symbol, formula, fixed = _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE[TALONS]
    assert symbol.startswith("TalonsOfTheEmperorPlaybook"), (
        "la ligne 1195 doit nommer le PLAYBOOK, pas l'ability -- vu %r" % symbol)
    assert "minDmg" in formula and fixed is True


def test_talons_le_profil_conditionnel_NE_PEUT_PAS_vivre_dans_le_registre_des_constantes():
    """`_PLAYBOOK_PROFILE_OVERRIDE` est un `{id: nom}` STATIQUE (mirror d'un `param_8` constant).
    Le profil de 1195 depend de `MeetSecondDamageProfileRequirement`, donc de l'ETAT -- l'y
    inscrire figerait une des deux branches. Et le handler l'emporterait de toute facon."""
    assert TALONS not in PA._PLAYBOOK_PROFILE_OVERRIDE


@pytest.mark.parametrize("level", [2, 8, 30, 45])
def test_talons_base_egale_minDmg_plus_le_flat_et_JAMAIS_la_moyenne(level):
    """`extra + base` du natif, avec `base = GetVariableForLevel(0xc)` et
    `extra = extraDmg x niveau(effet 1420)`.

    MUTANT qui mord : reprendre `avg(minDmg, maxDmg)` (le chemin generique). L'assertion de
    non-degenerescence ci-dessous garantit que ce niveau-la SEPARE bien les deux."""
    ab, cfg = _ability("TalonsOfTheEmperor", TALONS, level)
    mn = cfg.get_variable_for_level("minDmg", ab.level, 0, ab.multiplier)
    per = cfg.get_variable_for_level("extraDmg", ab.level, 0, ab.multiplier)
    assert ab.get_damage() != mn, (
        "niveau %d : la moyenne generique EGALE minDmg -- ce niveau ne discrimine pas, la garde "
        "serait muette" % level)
    # sans aucun effet 1420 : le flat vaut 0
    got = PA._talons_of_the_emperor_inputs(_SceneStub(), 1, 2, ab, cfg)
    assert got["base_override"] == mn, "niveau %d : base %r != minDmg %r" % (
        level, got["base_override"], mn)
    # avec DEUX instances de l'effet : `EffectLevelFormula` ACCUMULE (somme, pas `First`, pas `max`)
    from engine.runner.abilities.custodes import TOTE_USED_ABILITIES
    sc = _SceneStub(effects={1: [_EffStub(TOTE_USED_ABILITIES, 3),
                                 _EffStub(TOTE_USED_ABILITIES, 4)]})
    got2 = PA._talons_of_the_emperor_inputs(sc, 1, 2, ab, cfg)
    assert per > 0, "extraDmg nul au niveau %d : le volet flat serait indiscernable" % level
    assert got2["base_override"] == mn + per * 7, (
        "le niveau d'effet doit etre SOMME (3 + 4 = 7), pas pris au premier ni au max")


def test_talons_un_effet_CONSOMME_ne_compte_pas():
    """`EffectLevelFormula` n'accumule que les instances non consommees -- meme filtre que la face
    COMBAT, et c'est le MEME corps (`talons_used_abilities_level_from_effects`)."""
    from engine.runner.abilities.custodes import TOTE_USED_ABILITIES
    ab, cfg = _ability("TalonsOfTheEmperor", TALONS, 30)
    mn = cfg.get_variable_for_level("minDmg", ab.level, 0, ab.multiplier)
    sc = _SceneStub(effects={1: [_EffStub(TOTE_USED_ABILITIES, 5, consumed=True)]})
    assert PA._talons_of_the_emperor_inputs(sc, 1, 2, ab, cfg)["base_override"] == mn


def test_talons_le_compteur_est_le_MEME_CORPS_que_la_face_COMBAT():
    """Un fork COMBAT/DECISION du meme corps natif est precisement ce que le foyer partage
    interdit : les deux faces liraient des niveaux differents sans que rien ne rougisse."""
    from engine.runner.abilities import custodes as C
    assert hasattr(C, "talons_used_abilities_level_from_effects")
    assert C.talons_used_abilities_level_from_effects(
        [_EffStub(C.TOTE_USED_ABILITIES, 2), _EffStub(C.TOTE_USED_ABILITIES, 3)]) == 5
    assert C.talons_used_abilities_level_from_effects([]) == 0


def test_talons_ne_pose_AUCUN_hits_override():
    """Le natif rappelle `GetHits` (jamais `GetHits2`) dans les DEUX branches de profil : seul le
    PROFIL change. Poser un `hits_override` serait inventer une surcharge inexistante."""
    ab, cfg = _ability("TalonsOfTheEmperor", TALONS, 30)
    assert "hits_override" not in PA._talons_of_the_emperor_inputs(_SceneStub(), 1, 2, ab, cfg)


def test_talons_sans_substrat_DSL_le_profil_reste_celui_PAR_DEFAUT():
    """`scene.units` vide -> le predicat n'est pas evaluable -> AUCUN `profile_override`, donc le
    generique applique `damageProfile`. C'est la branche `else` NATIVE, pas une valeur devinee."""
    ab, cfg = _ability("TalonsOfTheEmperor", TALONS, 30)
    assert "profile_override" not in PA._talons_of_the_emperor_inputs(_SceneStub(), 1, 2, ab, cfg)


def test_talons_les_DEUX_profils_existent_bien_dans_le_gameconfig():
    """Si `damageProfile_2` disparaissait, le port cesserait SILENCIEUSEMENT de basculer -- et la
    face COMBAT, elle, rendrait `None` (aucun profil a passer). Le fait est re-derive, pas ecrit."""
    consts = (GC.ability("TalonsOfTheEmperor") or {}).get("constants") or {}
    assert consts.get("damageProfile"), "damageProfile absent du kit 1195"
    assert consts.get("damageProfile_2"), "damageProfile_2 absent du kit 1195"
    assert consts["damageProfile"] != consts["damageProfile_2"], (
        "les deux profils sont EGAUX : la bascule serait inobservable, et cette garde muette")


def test_talons_les_cles_SUFFIXEES_de_degat_n_existent_PAS():
    """Le natif ne bascule QUE le profil : il ne lit ni `minDmg_2` ni `nrOfHits_2`. Leur absence du
    kit est ce qui rend une bascule de base impossible a ecrire par megarde."""
    v = (GC.ability("TalonsOfTheEmperor") or {}).get("variables") or {}
    c = (GC.ability("TalonsOfTheEmperor") or {}).get("constants") or {}
    assert "minDmg_2" not in v and "maxDmg_2" not in v
    assert "nrOfHits_2" not in c


# =============================================================================================
# ETAGE 2 -- 1198 : UNE UTILITE DE PV, ET UN VETO EN TETE DE BOUCLE
# =============================================================================================
def test_euphoric_est_inscrit_avec_son_seuil_et_sa_base_NonComparable():
    """Non inscrit => l'IA ne propose JAMAIS l'ability par cette voie (no-op silencieux).

    `MIN_UTILITY = 1` vient du `.cctor` de la classe, LU par `EvaluateNonComparable` lui-meme --
    ce n'est PAS le `Fix64(10)` que `ComparablePlaybook<T>$$.cctor` ecrit pour la famille
    Comparable."""
    assert EUPHORIC in PLAYBOOKS, "%d absent de PLAYBOOKS" % EUPHORIC
    pb = PLAYBOOKS[EUPHORIC]
    assert type(pb).__name__ == "EuphoricStrikesPlaybook"
    assert pb.MIN_UTILITY == 1.0
    assert pb.PRIORITY == 0, "1198 est hors NATIVE_PRIORITY (sweep exhaustif #170)"
    assert isinstance(pb, _PlanTargetPlaybook), (
        "1198 porte une config de degat, donc ses paires (cible, tuile) sont dans `attackPlans` : "
        "le sweep de `_PlanTargetPlaybook` est ATTEINT (contraste avec les MoW de #970, dont le "
        "`reach_nc` vide rendait cette base inerte)")


def test_euphoric_est_declaree_NON_COMPARABLE_donc_sans_degat_fabrique():
    """Sans cette entree, le port fabriquerait depuis `minDmg`/`maxDmg` un `ProbableDamageEvent`
    que le natif n'emet jamais -- et 1198 PORTE une config de degat, donc le piege est arme."""
    assert makes_damage_predictions("EuphoricStrikes") is False
    kit = GC.ability("EuphoricStrikes") or {}
    assert (kit.get("variables") or {}).get("minDmg"), (
        "1198 n'a plus de config de degat : le piege que cette garde surveille a disparu, et "
        "l'assertion ci-dessus ne prouve donc plus rien")


def _ctx_euphoric(hp_by_id, scene=None):
    return NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                     hp_cur_by_id=hp_by_id, scene=scene)


def test_euphoric_utilite_egale_les_PV_COURANTS_de_la_cible():
    """`Fix64(GetStat(entity, 5 = Health, 0, 0))` -- les deux derniers arguments sont le litteral
    `0`, donc la valeur ABSOLUE, pas la part en pourcentage de `GetStat(Health, 1)`.

    MUTANT qui mord : rendre `hpmax` ou un pourcentage."""
    pb = PLAYBOOKS[EUPHORIC]
    assert pb.evaluate_non_comparable((0, 0), 50, _ctx_euphoric({50: 137})) == 137.0
    assert pb.evaluate_non_comparable((0, 0), 50, _ctx_euphoric({50: 1})) == 1.0


def test_euphoric_vise_la_cible_la_PLUS_ROBUSTE_pas_la_plus_faible():
    """Le sens de l'utilite est celui du decompile : PV COURANTS, donc `argmax`. L'inverser serait
    un contresens muet (l'IA gaspillerait la marque +crit sur une unite mourante)."""
    pb = PLAYBOOKS[EUPHORIC]
    ctx = _ctx_euphoric({50: 10, 51: 900})
    assert pb.evaluate_non_comparable((0, 0), 51, ctx) > pb.evaluate_non_comparable((0, 0), 50, ctx)


def test_euphoric_PV_non_mesures_ne_fabriquent_aucune_utilite():
    """Cible absente de `hp_cur_by_id` -> `None`, jamais un 0 qui se lirait comme une mesure."""
    assert PLAYBOOKS[EUPHORIC].evaluate_non_comparable((0, 0), 99, _ctx_euphoric({50: 137})) is None


def test_euphoric_le_VETO_WillNormalAttackKill_mord(monkeypatch):
    """`if (WillNormalAttackKill(...)) continue;` -- PREMIERE instruction du corps de boucle.

    Le patch porte sur le FOYER `engine.playbook.base.will_normal_attack_kill`, que
    `_base._will_normal_attack_kill` importe DANS sa fonction (forme C) : il mord donc. La
    contre-epreuve est dans le test suivant -- un patcheur qui ne mord pas rendrait cette garde
    VERTE pour de mauvaises raisons."""
    pb = PLAYBOOKS[EUPHORIC]
    ctx = _ctx_euphoric({50: 137})
    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill",
                        lambda *a, **k: True)
    assert pb.evaluate_non_comparable((0, 0), 50, ctx) is None, "le VETO natif ne mord pas"


def test_euphoric_le_patcheur_du_VETO_est_bien_MORDANT(monkeypatch):
    """CONTRE-EPREUVE du test precedent : le MEME point de substitution, force a `False`, doit
    laisser passer l'utilite. Sans elle, un patch INERTE (forme A) rendrait le test ci-dessus vert
    par accident -- la faute exacte qui a coute 28 fichiers rouges a #484."""
    pb = PLAYBOOKS[EUPHORIC]
    ctx = _ctx_euphoric({50: 137})
    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill",
                        lambda *a, **k: False)
    assert pb.evaluate_non_comparable((0, 0), 50, ctx) == 137.0, (
        "le point de substitution n'est PAS celui que le port emprunte : la garde du VETO ne "
        "prouve alors rien")


def test_euphoric_la_trace_ne_porte_AUCUNE_prediction_d_ABILITY():
    """`EvaluateNonComparable` ne construit qu'UN `ProbableDamageEvent`, celui du gate. Recopier la
    forme de `KillMaimBurn` -- qui porte le MEME gate -- en emettrait un SECOND, inexistant.

    `ctx.scene is None` -> `[]` : sans predicteur le port n'invente aucune trace."""
    pb = PLAYBOOKS[EUPHORIC]
    assert pb.damage_predictions((0, 0), 50, _ctx_euphoric({50: 137})) == []


def test_euphoric_la_trace_du_gate_porte_son_ETIQUETTE_et_reste_UNIQUE(monkeypatch):
    """Avec un predicteur, la sequence vaut exactement `[("WillNormalAttackKill", <pred>)]`."""
    pb = PLAYBOOKS[EUPHORIC]
    sentinelle = object()
    monkeypatch.setattr(
        "engine.playbook.prediction.normal_attack.make_normal_attack_predictions",
        lambda *a, **k: type("_E", (), {"prediction": sentinelle})())
    seq = pb.damage_predictions((0, 0), 50, _ctx_euphoric({50: 137}, scene=object()))
    assert [t for t, _ in seq] == ["WillNormalAttackKill"], (
        "la trace doit porter UN SEUL event, etiquete par le site natif qui le construit")
    assert seq[0][1] is sentinelle, "le patcheur de la trace n'a pas mordu"


# =============================================================================================
# ETAGE 3 -- LES TROIS VERDICTS, VERROUILLES (un jumeau livre est pire qu'un trou)
# =============================================================================================
def test_1184_est_deja_portee_par_la_route_BESPOKE():
    """`MomentShackle` est une Comparable qui OVERRIDE `EvaluateInternal` en entier : elle
    n'apparait dans AUCUN des trois registres que l'audit de couverture interroge, d'ou son
    classement en « non portee ». Elle l'est -- par `playbook/bespoke.py`."""
    from engine.playbook.bespoke import BESPOKE_SELFCAST
    assert MOMENT in {int(k) for k in BESPOKE_SELFCAST}
    from engine.playbook.static_threshold_gate import NOT_REGISTERED
    assert MOMENT in NOT_REGISTERED, (
        "1184 doit rester HORS du registre `StaticUtilityThresholdPlaybook` : son gate vit dans le "
        "generateur bespoke, l'y inscrire serait un port MORT")


def test_1191_est_deja_portee_par_le_registre_des_entrees():
    """`MartialInspiration` : base `round(minDmg x buff)` et `hits = 1` -- exactement ce que la
    table `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` NOMME. RELUE, pas re-ecrite."""
    assert MARTIAL in PA._MAKE_DMG_INPUT_OVERRIDES
    assert PA._MAKE_DMG_INPUT_OVERRIDES[MARTIAL] is PA._martial_inspiration_inputs
    _, formula, fixed = _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE[MARTIAL]
    assert "hits = 1" in formula and fixed is True


def test_1196_est_SANS_CONTENU_PROPRE_et_le_reste():
    """`LashOfTormentPlaybook$$MakeDamagePredictions` = `GetDamage` / `GetHits` /
    `GetDamageProfile` -> `GenerateMultiHitAttackPredictions`. C'est le chemin GENERIQUE strict :
    l'inscrire a un registre d'override serait un port SPECULATIF qui divergerait du natif.

    Meme verdict, et meme forme de verrou, que `LeadingTheCharge` (1204) dans #945."""
    assert LASH not in PA._MAKE_DMG_INPUT_OVERRIDES
    assert LASH not in PA._PLAYBOOK_PROFILE_OVERRIDE
    assert LASH not in PLAYBOOKS, "1196 est une Comparable : elle n'a rien a faire dans PLAYBOOKS"
    assert makes_damage_predictions("LashOfTorment") is True
    assert ActiveAbilityType.LashOfTorment in _PREDICTION_MINMAX_RANDOM_READ, (
        "1196 est de la famille (b) `MinMaxDamage(random)` -- LUE aux xrefs du corps partage, elle "
        "coincide avec le defaut ; retirer cette entree effacerait le fait qu'elle a ete LUE")
    assert LASH not in _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE
