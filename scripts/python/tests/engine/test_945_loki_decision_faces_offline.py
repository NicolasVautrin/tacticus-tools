"""#945 -- les SIX faces DECISION du lot `IdunBattle.AI.Playbook.Loki.*`, gardees SANS runner.

Ce fichier garde les points ou une lecture distraite du decompile produirait un port qui ne rougit
nulle part ailleurs. Chacun est un piege REEL, rencontre pendant la RE :

  1. **QUATRE bases lues dans `classes.tsv`, pas dans le `.ctor`.** Les quatre `.ctor` NOMMENT
     `ComparablePlaybook<...>$$.ctor` (corps trivial DEDUPLIQUE) alors que les quatre classes
     derivent de `NonComparablePlaybook`1`. Meme piege que #487-r1 / #572-r2.
  2. **TROIS provenances differentes pour le meme `MIN_UTILITY`.** `AlphaWarrior` le tient d'un
     `.cctor` ; `StormOfWrath` le construit INLINE dans la methode ; `AdaptiveStrategy` et
     `CalibaniteGreatsword` n'en ont AUCUN (Bucket ctor 2-ARG) -- pour la premiere le seuil reel
     est le `if (1 < n)` du corps. Inventer un `.cctor` inexistant, ou l'oublier, change le
     comportement dans les deux sens.
  3. **`AdaptiveStrategy` ancre son compte sur `Target`, pas sur `Caster`** -- alors que
     `...AdaptiveStrategyAbility$$ExecuteBehaviour` ancre sur `Caster`. Ecart NATIF entre les deux
     faces ; recopier la face COMBAT donnerait un compte faux sans lever.
  4. **`GetChainedUnits` inclut la CIBLE** (`adj.Add(tile)` avant l'enumeration) : une cible isolee
     vaut 1, pas 0. C'est ce qui donne son sens au seuil 2.
  5. **`AlphaWarrior` est un VETO, pas un score** : utilite booleenne + `MIN_UTILITY = 1`.
  6. **`CalibaniteGreatsword` est un XOR**, pas une condition simple : il ALLUME le sweep quand il
     servirait et l'ETEINT quand il ne sert plus. Porter la moitie de la formule laisserait
     l'ability collee en position haute (ou basse) sans que rien ne le signale.
  7. **`BrazierOfHolyFire` n'appelle PAS `GetHits`** : `ConditionalAmount(HasTrait(target, Daemon),
     nrOfHits_2, nrOfHits)` -- 4 coups contre un Daemon, 2 sinon, et SANS `GetDefaultAttackHits`.
  8. **`LeadingTheCharge` n'a AUCUN contenu propre** : son `MakeDamagePredictions` est
     structurellement identique a celui de `LightOfSanguinius`, que le port traite deja par le
     chemin generique. Ce fichier VERROUILLE ce verdict, pour qu'un lecteur ne le re-porte pas.

Aucune valeur de gameplay n'est ecrite en dur : les magnitudes (`nrOfHits`, `nrOfHits_2`, portee
des armes du summon) sont re-derivees du gameconfig ; seuls la STRUCTURE, les SEUILS lus au
decompile et les FERMETURES sont assertes.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe le registre `PLAYBOOKS` (donc tout
    # `engine.playbook.noncomparable`), `active_ability` (donc `_SPECIAL_ABILITY_CLASSES` et les
    # familles de moyenne de #344) et `playbook.prediction.abilities`. Sa fermeture d'import couvre
    # l'essentiel des deux faces DECISION.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire : les seuils (`2`, `1`, le
    # `if (1 < n)`) sont ceux LUS au decompile, les magnitudes viennent du gameconfig.
    "build": False,
    # offline pur, aucun runner, < 2 s.
    "toujours": True,
    "raison": "Gardes OFFLINE des six faces DECISION du lot Loki (#945) : bases NonComparable, "
              "les trois provenances de MIN_UTILITY, l'ancre Target d'AdaptiveStrategy, "
              "l'inclusion de la cible dans GetChainedUnits, le VETO d'AlphaWarrior, le XOR de "
              "CalibaniteGreatsword, les hits conditionnels au trait Daemon de BrazierOfHolyFire, "
              "et le verdict SANS CONTENU PROPRE de LeadingTheCharge.",
}

import pytest

import gameconfig as GC
import hexgeo

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.playbook.noncomparable import PLAYBOOKS
from engine.playbook.noncomparable._base import NCContext

ADAPTIVE = int(ActiveAbilityType.AdaptiveStrategy)         # 0x3ed = 1005
STORM = int(ActiveAbilityType.StormOfWrath)                # 0x3fb = 1019
BRAZIER = int(ActiveAbilityType.BrazierOfHolyFire)         # 0x411 = 1041
ALPHA = int(ActiveAbilityType.AlphaWarrior)                # 0x458 = 1112
CALIBANITE = int(ActiveAbilityType.CalibaniteGreatsword)   # 0x4a5 = 1189
LEADING = int(ActiveAbilityType.LeadingTheCharge)          # 0x4b4 = 1204

#: Un visualId reel pour chaque role, DERIVE du gameconfig au lieu d'etre suppose.
HERO_ALLY = "necroWarden"          # traits : Hero (le porteur de 1005 lui-meme)
NONHERO_ALLY = "tyranSmnWarrior"   # traits : Summon / Synapse / BigTarget -- PAS Hero


def _voisins(p):
    """Voisinage NATIF vu par le port quand `neigh_by_pos` est absent : le repli GEOMETRIQUE de
    `battle_query.is_adjacent` (couronne hex `distance == 1`). Les tests ci-dessous laissent
    volontairement `neigh_by_pos = None` -- ils gardent la FORMULE, pas le substrat de voisinage
    (qui a son propre cliquet, #433-r4-r1-r4-r2)."""
    return [(q[0], q[1]) for q in hexgeo.neighbors(p[0], p[1])]


def _ctx(**kw) -> NCContext:
    base = dict(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    base.update(kw)
    return NCContext(**base)


def _obs(sq, team, vid, pos, dead=False):
    return {"squadId": sq, "teamId": team, "visualId": vid,
            "col": pos[0], "row": pos[1], "isDead": dead}


def _targets_stub(uid, ability_id, targets, kind="unit"):
    """Mirror minimal de l'RPC `abilityTargets` : seule la vue `fromHere` est peuplee -- c'est
    celle que les trois playbooks ally/tile-targeted consomment (mirror de
    `GetEligibleTargetsSelectable(caster, casterPosition.MainTile)`)."""
    def _call(u, a):
        if u != uid or a != ability_id:
            return {}
        if kind == "unit":
            fh = [{"targetId": t} for t in targets]
        else:
            fh = [{"kind": "tile", "tile": {"col": t[0], "row": t[1]}} for t in targets]
        return {"units": [{"unitId": uid, "abilities": [{"abilityId": ability_id, "fromHere": fh}]}]}
    return _call


# =============================================================================================
# ETAGE 1 -- LES QUATRE PLAYBOOKS SONT AU REGISTRE, AVEC LEUR SEUIL LU (pieges 1 et 2)
# =============================================================================================
@pytest.mark.parametrize("aid,classe,seuil", [
    (ADAPTIVE, "AdaptiveStrategyPlaybook", 2.0),
    (STORM, "StormOfWrathPlaybook", 2.0),
    (ALPHA, "AlphaWarriorPlaybook", 1.0),
    (CALIBANITE, "CalibaniteGreatswordPlaybook", 0.0),
])
def test_le_playbook_est_inscrit_avec_son_seuil(aid, classe, seuil):
    """Non inscrit => l'IA ne propose JAMAIS l'ability par cette voie (no-op silencieux).

    Les trois provenances du seuil (piege 2) : `.cctor` pour 1112, litteral INLINE pour 1019,
    AUCUN pour 1005 (dont le seuil est le `if (1 < n)` du corps) et 1189 (utilite constante)."""
    assert aid in PLAYBOOKS, "%d absent de PLAYBOOKS" % aid
    pb = PLAYBOOKS[aid]
    assert type(pb).__name__ == classe
    assert pb.MIN_UTILITY == seuil, "MIN_UTILITY lu = %s, obtenu %s" % (seuil, pb.MIN_UTILITY)
    assert pb.PRIORITY == 0, "aucune des quatre n'est dans NATIVE_PRIORITY (sweep exhaustif #170)"


def test_les_quatre_sont_declarees_NON_COMPARABLE_donc_sans_degat_fabrique():
    """`_NONCOMPARABLE_ABILITIES` : le natif n'emet AUCUN `ProbableDamageEvent` pour elles
    (`frida/methods.tsv` ne leur declare aucun `Make*Predictions`). Sans cette entree, le port
    fabriquait un degat depuis `minDmg`/`maxDmg` du gameconfig -- exactement le faux positif de
    #109 sur `GauntletsOfUltramar`."""
    from engine.entities.abilities.active_ability import makes_damage_predictions
    for nom in ("AdaptiveStrategy", "StormOfWrath", "AlphaWarrior", "CalibaniteGreatsword"):
        assert makes_damage_predictions(nom) is False, "%s doit etre NonComparable" % nom
    # Contre-epreuve : les DEUX Comparable du meme lot restent, elles, sur le chemin de prediction.
    for nom in ("BrazierOfHolyFire", "LeadingTheCharge"):
        assert makes_damage_predictions(nom) is True, \
            "%s est un ComparablePlaybook (MakeDamagePredictions declaree)" % nom


# =============================================================================================
# ETAGE 2 -- ADAPTIVE STRATEGY : L'ANCRE EST LA CIBLE, LE FILTRE EST `Hero` (piege 3)
# =============================================================================================
def _ctx_adaptive(voisins_de_la_cible, cible=(3, 3), caster=(0, 0)):
    """Board minimal : le caster en `caster` (Hero, donc jamais compte), la cible en `cible`, et
    une unite ALLIEE par entree de `voisins_de_la_cible` -- chaque entree est `(delta_index, vid)`
    ou `delta_index` designe un voisin hex de la cible."""
    ring = _voisins(cible)
    units = [{"id": 1, "pos": {"col": caster[0], "row": caster[1]}, "visualId": HERO_ALLY},
             {"id": 9, "pos": {"col": cible[0], "row": cible[1]}, "visualId": NONHERO_ALLY}]
    obs = [_obs(1, 1, HERO_ALLY, caster), _obs(9, 1, NONHERO_ALLY, cible)]
    for k, (idx, vid) in enumerate(voisins_de_la_cible):
        uid = 20 + k
        p = ring[idx]
        units.append({"id": uid, "pos": {"col": p[0], "row": p[1]}, "visualId": vid})
        obs.append(_obs(uid, 1, vid, p))
    return _ctx(uid=1, origin=caster, reach_nc=[caster], units=units, obs_units=obs,
                ability_targets=_targets_stub(1, ADAPTIVE, [9]))


def test_adaptive_compte_les_allies_NON_HEROS_adjacents_A_LA_CIBLE():
    """`Count(Friends(Caster, UnitsWithoutTrait(AdjacentUnits(Target, 1, 3), Hero, 3), 3))`.

    Deux allies non-heros colles a la cible -> 2 -> l'action est generee (gate `if (1 < n)`)."""
    pb = PLAYBOOKS[ADAPTIVE]
    ctx = _ctx_adaptive([(0, NONHERO_ALLY), (1, NONHERO_ALLY)])
    assert pb.evaluate_non_comparable(ctx.origin, 9, ctx) == 2.0
    cands = pb.generate_candidates(ctx)
    assert len(cands) == 1 and cands[0]["target"] == 9 and cands[0]["pred"] == 2.0


def test_adaptive_EXCLUT_les_heros_du_compte():
    """`UnitsWithoutTrait(..., 0x10 = UnitTrait.Hero)` -- « NonCharacterFriends ». Un allie HEROS
    adjacent ne compte pas : deux voisins dont un heros -> 1 -> SOUS le seuil, rien n'est genere.

    MUTANT qui mord : retirer le filtre `Hero` ferait passer ce compte a 2 et generer une action.
    """
    pb = PLAYBOOKS[ADAPTIVE]
    ctx = _ctx_adaptive([(0, NONHERO_ALLY), (1, HERO_ALLY)])
    assert UnitTrait.Hero.name in (GC.unit(HERO_ALLY) or {}).get("traits", []), \
        "le montage exige que %s porte bien le trait Hero" % HERO_ALLY
    assert pb.evaluate_non_comparable(ctx.origin, 9, ctx) == 1.0
    assert pb.generate_candidates(ctx) == [], "1 < MIN_UTILITY 2 -> aucune action"


def test_adaptive_ancre_sur_la_CIBLE_et_non_sur_le_CASTER():
    """LE piege 3, rendu DISTINGUABLE : deux allies non-heros colles au CASTER et AUCUN colle a la
    cible. Le playbook natif compte les voisins de `Target@+0x60` -> **0**. Un port qui aurait
    recopie l'ancre `Caster@+0x48` de `...AdaptiveStrategyAbility$$ExecuteBehaviour` rendrait 2 et
    genererait une action que le natif ne genere pas."""
    pb = PLAYBOOKS[ADAPTIVE]
    caster, cible = (0, 0), (5, 5)
    ring_caster = _voisins(caster)
    units = [{"id": 1, "pos": {"col": caster[0], "row": caster[1]}, "visualId": HERO_ALLY},
             {"id": 9, "pos": {"col": cible[0], "row": cible[1]}, "visualId": NONHERO_ALLY}]
    obs = [_obs(1, 1, HERO_ALLY, caster), _obs(9, 1, NONHERO_ALLY, cible)]
    for k, p in enumerate(ring_caster[:2]):
        units.append({"id": 30 + k, "pos": {"col": p[0], "row": p[1]}, "visualId": NONHERO_ALLY})
        obs.append(_obs(30 + k, 1, NONHERO_ALLY, p))
    ctx = _ctx(uid=1, origin=caster, reach_nc=[caster], units=units, obs_units=obs,
               ability_targets=_targets_stub(1, ADAPTIVE, [9]))
    assert pb.evaluate_non_comparable(caster, 9, ctx) == 0.0, \
        "ancre = Target : les voisins du CASTER ne comptent pas"
    assert pb.generate_candidates(ctx) == []


def test_adaptive_ne_compte_ni_la_cible_elle_meme_ni_un_ennemi():
    """`AdjacentUnits(T)` = `Units(AdjacentTiles(T)) - T` (la cible n'est jamais son propre voisin)
    et `Friends(Caster, ...)` filtre par camp : une unite d'equipe ADVERSE collee a la cible ne
    compte pas."""
    pb = PLAYBOOKS[ADAPTIVE]
    cible = (3, 3)
    ring = _voisins(cible)
    units = [{"id": 1, "pos": {"col": 0, "row": 0}, "visualId": HERO_ALLY},
             {"id": 9, "pos": {"col": cible[0], "row": cible[1]}, "visualId": NONHERO_ALLY},
             {"id": 40, "pos": {"col": ring[0][0], "row": ring[0][1]}, "visualId": NONHERO_ALLY}]
    obs = [_obs(1, 1, HERO_ALLY, (0, 0)), _obs(9, 1, NONHERO_ALLY, cible),
           _obs(40, 2, NONHERO_ALLY, ring[0])]                 # equipe 2 = ADVERSE
    ctx = _ctx(uid=1, units=units, obs_units=obs)
    assert pb.evaluate_non_comparable((0, 0), 9, ctx) == 0.0


# =============================================================================================
# ETAGE 3 -- STORM OF WRATH : LA CHAINE INCLUT LA CIBLE (piege 4)
# =============================================================================================
def _ctx_chaine(chaine, cible_team=2):
    """Une file d'unites deux a deux adjacentes en partant de `(0, 0)` ; `chaine` = la liste des
    equipes, la premiere entree etant la CIBLE."""
    pos = [(0, 0)]
    while len(pos) < len(chaine):
        pos.append(_voisins(pos[-1])[0])
    obs = [_obs(100 + i, t, NONHERO_ALLY, p) for i, (t, p) in enumerate(zip(chaine, pos))]
    return _ctx(uid=1, obs_units=obs), 100


def test_storm_une_cible_ISOLEE_vaut_UN_et_reste_sous_le_seuil():
    """`GetChainedUnitsInternal` ajoute la tuile de `unit` a son propre voisinage (`adj.Add(tile)`)
    -> la cible entre dans le set des le premier niveau. Une cible isolee vaut donc **1**, jamais
    0 -- et `MIN_UTILITY = 2` la rejette.

    MUTANT qui mord : ne pas inclure la cible rendrait 0 ici ET 1 sur la paire du test suivant,
    donc plus AUCUN cast de 1019 ne serait jamais propose."""
    pb = PLAYBOOKS[STORM]
    ctx, base = _ctx_chaine([2])
    assert pb.evaluate_non_comparable((0, 0), base, ctx) == 1.0
    assert pb.evaluate_non_comparable((0, 0), base, ctx) < pb.MIN_UTILITY


def test_storm_compte_la_chaine_TRANSITIVE_des_amis_de_la_cible():
    """La recursion propage de proche en proche : trois unites de la MEME equipe alignees valent
    3, meme si la troisieme n'est pas adjacente a la cible."""
    pb = PLAYBOOKS[STORM]
    ctx, base = _ctx_chaine([2, 2, 2])
    assert pb.evaluate_non_comparable((0, 0), base, ctx) == 3.0


def test_storm_s_arrete_au_changement_d_equipe():
    """`onlyFriends = true` (le litteral `1` du call-site) : la chaine ne traverse pas un ennemi
    de la cible, et ne reprend donc pas de l'autre cote.

    MUTANT qui mord : passer `onlyFriends = false` compterait 3 ici au lieu de 1."""
    pb = PLAYBOOKS[STORM]
    ctx, base = _ctx_chaine([2, 1, 2])
    assert pb.evaluate_non_comparable((0, 0), base, ctx) == 1.0


def test_storm_ignore_les_MORTS():
    """`GetUnit(tile)` passe par `TileContentComponent$$IsFilled` : une depouille ne remplit plus
    sa tuile. Substrat : `obs_units.isDead` (`decisionView` GARDE les morts)."""
    pb = PLAYBOOKS[STORM]
    ctx, base = _ctx_chaine([2, 2, 2])
    for u in ctx.obs_units:
        if u["squadId"] == base + 1:
            u["isDead"] = True
    assert pb.evaluate_non_comparable((0, 0), base, ctx) == 1.0, \
        "la chaine est coupee par la depouille"


def test_storm_ne_construit_AUCUNE_prediction_de_degat():
    """`frida/methods.tsv` ne declare a `StormOfWrathPlaybook` que `..ctor` et
    `EvaluateNonComparable` : la sequence que l'oracle `ncPlaybookPredict` voit est VIDE."""
    assert PLAYBOOKS[STORM].damage_predictions((0, 0), 1, _ctx()) == []


# =============================================================================================
# ETAGE 4 -- ALPHA WARRIOR : UN VETO, PAS UN SCORE (piege 5)
# =============================================================================================
def _portee_du_summon():
    """`Max(w.Range ?? 1)` sur les armes du `constants.unitId` de 1112 -- DERIVE du gameconfig.

    Les deux helpers ont demenage dans le foyer PARTAGE
    `engine.playbook.noncomparable.summon_attack_range` (#967, slot 195 = les DEUX branches) et y
    sont PUBLICS (`summon_id`, `summon_attack_range`). `alpha_warrior` n'en est plus qu'un lecteur
    en FORME B : re-exporter les anciens noms prives y aurait fabrique une seconde adresse pour un
    foyer unique. FORME B ici aussi -- un patcheur qui substitue `summon_attack_range.<nom>` mord.

    ⚠ La SIGNATURE a change avec l'adresse : l'ancien `alpha_warrior._summon_id` prenait un
    ability_ID (int) et faisait lui-meme `ActiveAbilityType(id).name` ; le foyer prend le NOM.
    Un simple re-export des anciens noms n'aurait donc PAS repare ce test -- il aurait rendu
    `None` en silence (l'int ne matche aucune cle du gameconfig), et l'assertion serait tombee
    plus loin, sur une valeur, au lieu de l'import. C'est le meme appel que fait le playbook."""
    import engine.playbook.noncomparable.summon_attack_range as SAR
    return SAR.summon_attack_range(SAR.summon_id(ActiveAbilityType(ALPHA).name))


def _ctx_alpha(tuile, ennemi, turns_started=2):
    class _Scene:
        def turns_started(self, _uid):
            return turns_started
    units = [{"id": 1, "pos": {"col": 0, "row": 0}, "visualId": "tyranWingedPrime"}]
    enemies = [{"id": 50, "pos": {"col": ennemi[0], "row": ennemi[1]}}]
    return _ctx(uid=1, origin=(0, 0), reach_nc=[(0, 0)], units=units, enemies=enemies,
                epos=[ennemi], scene=_Scene(),
                tile_id_by_pos={tuile: 900},
                ability_targets=_targets_stub(1, ALPHA, [tuile], kind="tile"))


def test_alpha_la_portee_du_summon_est_celle_de_son_ARME_LA_PLUS_LONGUE():
    """`foreach w in GetUnitConfig(unitId).weapons: range = Max(range, w.Range ?? 1)`. Le `?? 1`
    est LU : une arme de melee compte pour 1, pas pour 0. Valeur re-derivee du gameconfig."""
    import engine.playbook.noncomparable.summon_attack_range as SAR
    sid = SAR.summon_id(ActiveAbilityType(ALPHA).name)   # le foyer #967 prend le NOM, pas l'id
    assert sid, "constants.unitId de 1112 introuvable"
    armes = (GC.unit(sid) or {}).get("weapons") or []
    attendu = max(int(w.get("Range") or 1) for w in armes)
    assert _portee_du_summon() == attendu
    assert attendu >= 1


def test_alpha_accepte_une_tuile_A_PORTEE_et_refuse_une_tuile_HORS_PORTEE():
    """L'utilite est BOOLEENNE et `MIN_UTILITY = 1` : hors portee -> util 0 -> rien.

    MUTANT qui mord : un `>=` au lieu du `>` du natif (`GetDistance > range -> false`) accepterait
    la tuile a `range + 1`."""
    pb = PLAYBOOKS[ALPHA]
    rng = _portee_du_summon()
    ennemi = (0, 0)
    # Une tuile a EXACTEMENT `rng` de l'ennemi, et une a `rng + 1`.
    dedans = next(p for p in [(c, r) for c in range(-8, 9) for r in range(-8, 9)]
                  if hexgeo.distance(p, ennemi) == rng)
    dehors = next(p for p in [(c, r) for c in range(-8, 9) for r in range(-8, 9)]
                  if hexgeo.distance(p, ennemi) == rng + 1)
    ctx_ok = _ctx_alpha(dedans, ennemi)
    assert pb.has_summon_target_in_attack_range_at_tile(ctx_ok, dedans) is True
    cands = pb.generate_candidates(ctx_ok)
    assert len(cands) == 1 and cands[0]["target"] == 900 and cands[0]["pred"] == 1.0
    ctx_ko = _ctx_alpha(dehors, ennemi)
    assert pb.has_summon_target_in_attack_range_at_tile(ctx_ko, dehors) is False
    assert pb.generate_candidates(ctx_ko) == [], "util 0 < MIN_UTILITY 1 -> VETO"


def test_alpha_sans_aucun_ennemi_ne_propose_rien():
    """`GetNearestEnemy` rend `null` -> `IsTargetInAttackRangeForSummon` refuse d'emblee."""
    pb = PLAYBOOKS[ALPHA]
    ctx = _ctx_alpha((1, 0), (0, 0))
    ctx.enemies = []
    assert pb.has_summon_target_in_attack_range_at_tile(ctx, (1, 0)) is False


def test_alpha_n_evalue_PAS_au_premier_tour_de_son_porteur():
    """Slot 4 = le corps FOLDE `AlphaWarriorPlaybook$$ShouldEvaluate` :
    `GetStat(unit, 0xc = TurnsStarted) > 1`. `turnsStarted` vaut 1 pendant le PREMIER tour.

    MUTANT qui mord : oublier ce gate ferait proposer 1112 des le tour 1."""
    pb = PLAYBOOKS[ALPHA]
    rng = _portee_du_summon()
    ennemi = (0, 0)
    dedans = next(p for p in [(c, r) for c in range(-8, 9) for r in range(-8, 9)]
                  if hexgeo.distance(p, ennemi) == rng)
    assert pb.should_evaluate(_ctx_alpha(dedans, ennemi, turns_started=2)) is True
    assert pb.should_evaluate(_ctx_alpha(dedans, ennemi, turns_started=1)) is False


# =============================================================================================
# ETAGE 5 -- CALIBANITE GREATSWORD : UN XOR (piege 6)
# =============================================================================================
class _SceneEffet:
    def __init__(self, present):
        self._present = present


def _ctx_calibanite(cond, has_effect, avec_triggered=False):
    """Montage MINIMAL qui pilote les deux membres du XOR par des leviers INDEPENDANTS :
    `cond` via `should_toggle` (substitue), `has_effect` via `scene_has_effect` (substitue)."""
    units = [{"id": 1, "pos": {"col": 0, "row": 0}, "visualId": "darkaCompanion"}]
    return _ctx(uid=1, origin=(0, 0), reach_nc=[(0, 0)], units=units)


@pytest.mark.parametrize("cond,has_effect,emet", [
    (True, False, True),     # le sweep servirait et il est ETEINT   -> ALLUMER
    (False, True, True),     # le sweep ne sert plus et il est ALLUME -> ETEINDRE
    (True, True, False),     # deja allume et utile                   -> rien
    (False, False, False),   # deja eteint et inutile                 -> rien
])
def test_calibanite_est_un_XOR_sur_les_quatre_combinaisons(monkeypatch, cond, has_effect, emet):
    """`if (cond) { if (!hasEffect) AddAction; return } ... if (hasEffect) AddAction`.

    MUTANT qui mord : remplacer le XOR par `cond` seul rend VRAI la 3e ligne (deja allume) et FAUX
    la 2e -- l'ability resterait collee en position haute et ne serait jamais eteinte."""
    import engine.playbook.noncomparable.calibanite_greatsword as CG
    pb = PLAYBOOKS[CALIBANITE]
    monkeypatch.setattr(CG.CalibaniteGreatswordPlaybook, "should_toggle", lambda self, c: cond)
    monkeypatch.setattr(CG.CalibaniteGreatswordPlaybook, "_has_sweep_effect",
                        lambda self, c: has_effect)
    cands = pb.generate_candidates(_ctx_calibanite(cond, has_effect))
    assert bool(cands) is emet
    if emet:
        assert cands[0]["target"] == 1, "cible = le CASTER (self-cast)"
        assert cands[0]["to"] is None, "GATE 2 : cast depuis l'ORIGINE uniquement"
        assert cands[0]["pred"] == float(0x7fffffff), "Fix64.op_Implicit(0x7fffffff)"


def test_calibanite_le_gate_de_triggered_ability_coupe_tout(monkeypatch):
    """GATE 1 `HasTriggeredAbility(caster, 0x5f2 = RedemptionOfTheRisen)` -> bucket VIDE, quel que
    soit le XOR. Le gate est INERTE dans le gameconfig `rnca9r7q6c` (aucune unite ne porte cette
    triggered ability) -- ce test le pilote donc par le substrat, et verifie AUSSI l'inertie."""
    import engine.playbook.noncomparable.calibanite_greatsword as CG
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    pb = PLAYBOOKS[CALIBANITE]
    monkeypatch.setattr(CG.CalibaniteGreatswordPlaybook, "should_toggle", lambda self, c: True)
    monkeypatch.setattr(CG.CalibaniteGreatswordPlaybook, "_has_sweep_effect", lambda self, c: False)
    monkeypatch.setattr(CG.CalibaniteGreatswordPlaybook, "_has_excluding_triggered_ability",
                        lambda self, c: True)
    assert pb.generate_candidates(_ctx_calibanite(True, False)) == []
    # Inertie MESUREE : le porteur reel ne porte pas la triggered ability.
    kit = GC.unit("darkaCompanion") or {}
    noms = (kit.get("activeAbilities") or []) + (kit.get("passiveAbilities") or [])
    assert TriggeredAbilityType.RedemptionOfTheRisen.name not in noms


def test_calibanite_sans_position_d_origine_ne_propose_rien():
    """GATE 2 : `casterPosition != GetUnitPosition(caster)` rejette toute tuile de move ; sans
    origine connue le port ne peut rien affirmer."""
    pb = PLAYBOOKS[CALIBANITE]
    assert pb.generate_candidates(_ctx(uid=1, origin=None)) == []


def test_calibanite_le_selecteur_extra_est_une_INTERSECTION():
    """`AdjacentEnemies(Caster, CasterTile, 1) op_BitwiseAnd AdjacentUnits(Target, 1, 3)`.

    MUTANT qui mord : une UNION (`op_Addition`) compterait l'ennemi qui n'est adjacent qu'a la
    tuile d'attaque -- ici 1 au lieu de 0, ce qui allumerait le sweep sans raison."""
    pb = PLAYBOOKS[CALIBANITE]
    tuile, cible = (0, 0), (4, 4)
    voisin_tuile_seul = _voisins(tuile)[0]
    commun = next((p for p in _voisins(tuile) if hexgeo.distance(p, (1, 0)) == 1), None)
    units = [{"id": 1, "pos": {"col": 0, "row": 0}, "visualId": "darkaCompanion"},
             {"id": 9, "pos": {"col": cible[0], "row": cible[1]}, "visualId": NONHERO_ALLY}]
    ctx = _ctx(uid=1, units=units, epos=[voisin_tuile_seul])
    assert pb._sweep_extra_count(ctx, tuile, 9) == 0, \
        "l'ennemi n'est adjacent qu'a la TUILE : l'intersection est vide"
    # Un ennemi adjacent AUX DEUX (cible collee a la tuile) : l'intersection est non vide.
    cible2 = _voisins(tuile)[1]
    units[1]["pos"] = {"col": cible2[0], "row": cible2[1]}
    commun2 = next(p for p in _voisins(tuile) if hexgeo.distance(p, cible2) == 1)
    ctx2 = _ctx(uid=1, units=units, epos=[commun2])
    assert pb._sweep_extra_count(ctx2, tuile, 9) == 1


# =============================================================================================
# ETAGE 6 -- BRAZIER OF HOLY FIRE : LES HITS SONT CONDITIONNELS AU TRAIT DE LA CIBLE (piege 7)
# =============================================================================================
def _brazier_ability():
    from engine.entities.abilities.active_ability import (BrazierOfHolyFireAbility,
                                                          _SPECIAL_ABILITY_CLASSES)
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    assert _SPECIAL_ABILITY_CLASSES.get("BrazierOfHolyFire") is BrazierOfHolyFireAbility
    cfg = AbilityConfiguration.from_gameconfig("BrazierOfHolyFire", GC.ability("BrazierOfHolyFire"))
    return BrazierOfHolyFireAbility(BRAZIER, caster=None, config=cfg)


def test_brazier_quatre_coups_contre_un_DAEMON_deux_sinon():
    """`ConditionalAmount(HasTrait(target, 0x3fb = UnitTrait.Daemon), nrOfHits_2, nrOfHits)`.

    Les deux valeurs sont RE-DERIVEES du gameconfig (`nrOfHits` / `nrOfHits_2`) : un rebalancement
    ne doit pas rougir ici, une inversion des deux branches, si.

    MUTANT qui mord : inverser `nrOfHits` et `nrOfHits_2` rendrait 2 coups contre un demon et 4
    contre tout le reste -- soit la moitie du degat predit face aux cibles que l'ability vise."""
    ab = _brazier_ability()
    c = GC.ability("BrazierOfHolyFire")["constants"]
    n1, n2 = int(c["nrOfHits"]), int(c["nrOfHits_2"])
    assert n1 != n2, "le montage exige que les deux constantes DIFFERENT (sinon la garde est vide)"
    assert ab.get_number_of_hits(()) == n1
    assert ab.get_number_of_hits((UnitTrait.Daemon.name,)) == n2
    assert ab.get_number_of_hits((UnitTrait.Hero.name,)) == n1, \
        "seul le trait Daemon bascule la branche"


def test_brazier_le_handler_d_entrees_est_au_registre_et_rend_les_hits():
    """`_MAKE_DMG_INPUT_OVERRIDES[1041]` -- sans lui, `generate_multi_hit_attack_prediction` lirait
    `ab.get_special_hits(is_melee)` = `GetDefaultAttackHits(nrOfHits + ExtraHits)`, ce que le
    playbook natif ne fait PAS."""
    from engine.playbook.prediction.abilities import (_MAKE_DMG_INPUT_OVERRIDES,
                                                      _brazier_of_holy_fire_inputs)
    assert _MAKE_DMG_INPUT_OVERRIDES.get(ActiveAbilityType.BrazierOfHolyFire) \
        is _brazier_of_holy_fire_inputs
    ab = _brazier_ability()
    c = GC.ability("BrazierOfHolyFire")["constants"]

    class _Scene:
        pass

    import engine.playbook.prediction.abilities as PA
    orig = PA._entity_traits
    try:
        PA._entity_traits = lambda scene, tid: ((UnitTrait.Daemon.name,) if tid == 7 else ())
        assert _brazier_of_holy_fire_inputs(_Scene(), 1, 7, ab, None) == \
            {"hits_override": int(c["nrOfHits_2"])}
        assert _brazier_of_holy_fire_inputs(_Scene(), 1, 8, ab, None) == \
            {"hits_override": int(c["nrOfHits"])}
    finally:
        PA._entity_traits = orig


def test_brazier_la_BASE_reste_la_moyenne_demi_vers_le_pair():
    """`<BrazierOfHolyFireAbility>$$GetDamageAmountMain` est le corps DEDUPLIQUE etiquete
    `StranglethornCannonAbility$$GetDamageAmountMain` -> `AActiveAbility$$MinMaxDamageAverage`.
    1041 doit donc rester dans la famille (a1) de #344, et le handler ne surcharge PAS la base."""
    from engine.entities.abilities.active_ability import (_A_VIA_GET_DAMAGE_AMOUNT_MAIN,
                                                          _PREDICTION_MINMAX_AVERAGE)
    assert ActiveAbilityType.BrazierOfHolyFire in _A_VIA_GET_DAMAGE_AMOUNT_MAIN
    assert ActiveAbilityType.BrazierOfHolyFire in _PREDICTION_MINMAX_AVERAGE
    from engine.playbook.prediction.abilities import _brazier_of_holy_fire_inputs
    ab = _brazier_ability()
    import engine.playbook.prediction.abilities as PA
    orig = PA._entity_traits
    try:
        PA._entity_traits = lambda scene, tid: ()
        out = _brazier_of_holy_fire_inputs(object(), 1, 2, ab, None)
    finally:
        PA._entity_traits = orig
    assert set(out) == {"hits_override"}, \
        "le handler ne touche NI la base NI le profil (deja justes) : %r" % (out,)


# =============================================================================================
# ETAGE 7 -- LEADING THE CHARGE : LE VERDICT « SANS CONTENU PROPRE », VERROUILLE (piege 8)
# =============================================================================================
def test_leading_the_charge_n_a_aucun_override_et_c_est_le_VERDICT():
    """`IdunBattle.AI.Playbook.Loki.LeadingTheChargePlaybook$$MakeDamagePredictions` est
    structurellement IDENTIQUE a `IdunBattle.AI.Playbook.LightOfSanguiniusPlaybook$$
    MakeDamagePredictions` (les deux corps ont ete decompiles et compares) :

        list = new List<ProbableDamageEvent>()
        damage = <X>Ability$$GetDamage(abilityState, isPrediction: 1)   # corps DEDUPLIQUE
                                                    # `StaffOfStarsAbility$$GetDamage`
                                                    # -> `AActiveAbility$$MinMaxDamage`
        hits   = AActiveAbility$$GetHits()
        prof   = AActiveAbility$$GetDamageProfile()
        list.AddRange(GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                                                        Target@+0x60, damage, hits,
                                                        Nullable(prof), null, 0))
        return list

    -- que des appels DIRECTS aux corps de la classe de base. C'est EXACTEMENT le chemin
    generique du port (`DefaultActiveAbilityPlaybook` cote natif), et `LightOfSanguinius` y est
    deja traite ainsi. Il n'y a donc RIEN a porter : 1204 ne doit apparaitre dans AUCUN des
    registres d'override, et sa seule inscription utile est la famille de moyenne (a2), qui y est
    deja.

    Ce test EXISTE pour que ce verdict ne se reperde pas : sans lui, la seule trace serait la
    prose, et le prochain lecteur re-porterait un handler inutile (ou pire, un handler FAUX)."""
    from engine.entities.abilities.active_ability import (_A_VIA_STAFF_OF_STARS_GET_DAMAGE,
                                                          _NONCOMPARABLE_ABILITIES,
                                                          _SPECIAL_ABILITY_CLASSES)
    from engine.playbook import REGISTRY as CUSTOM_PLAYBOOKS
    from engine.playbook.prediction.abilities import (_MAKE_DMG_EXTRA_EVENTS,
                                                      _MAKE_DMG_INPUT_OVERRIDES,
                                                      _MAKE_DMG_SELECTOR_ONLY,
                                                      _MAKE_DMG_TARGET_GATE,
                                                      _PLAYBOOK_PROFILE_OVERRIDE)
    assert ActiveAbilityType.LeadingTheCharge in _A_VIA_STAFF_OF_STARS_GET_DAMAGE, \
        "la base EST une moyenne demi-vers-le-pair (isPrediction = 1 au call-site)"
    assert "LeadingTheCharge" not in _NONCOMPARABLE_ABILITIES, "c'est un ComparablePlaybook"
    assert "LeadingTheCharge" not in _SPECIAL_ABILITY_CLASSES, \
        "aucune formule d'ability propre : le SET est `Target`, la cible principale seule"
    assert LEADING not in CUSTOM_PLAYBOOKS, \
        "aucun `CalculateCustomUtility` : la classe ne declare que `..ctor` et `MakeDamagePredictions`"
    for reg, nom in ((_MAKE_DMG_INPUT_OVERRIDES, "_MAKE_DMG_INPUT_OVERRIDES"),
                     (_PLAYBOOK_PROFILE_OVERRIDE, "_PLAYBOOK_PROFILE_OVERRIDE"),
                     (_MAKE_DMG_TARGET_GATE, "_MAKE_DMG_TARGET_GATE"),
                     (_MAKE_DMG_EXTRA_EVENTS, "_MAKE_DMG_EXTRA_EVENTS")):
        assert ActiveAbilityType.LeadingTheCharge not in reg and LEADING not in reg, \
            "1204 n'a AUCUN contenu propre -- une entree dans %s serait une invention" % nom
    assert LEADING not in _MAKE_DMG_SELECTOR_ONLY


def test_les_deux_comparables_du_lot_ne_sont_PAS_dans_le_registre_NonComparable():
    """Contre-epreuve de la ventilation lue dans `frida/classes.tsv` : 1041 et 1204 derivent de
    `ComparablePlaybook`1`, les quatre autres de `NonComparablePlaybook`1`."""
    assert BRAZIER not in PLAYBOOKS and LEADING not in PLAYBOOKS
    for aid in (ADAPTIVE, STORM, ALPHA, CALIBANITE):
        assert aid in PLAYBOOKS
