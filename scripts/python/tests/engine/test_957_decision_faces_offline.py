"""#957 -- les faces DECISION du 2e lot Loki, gardees SANS runner.

Ce fichier garde les points ou une lecture distraite du decompile produit un port qui ne rougit
nulle part ailleurs. Chacun est un piege REEL, rencontre pendant la RE :

  1. **TROIS bases lues dans `classes.tsv`, pas dans le `.ctor`.** Les trois `.ctor` NOMMENT
     `ComparablePlaybook<...>$$.ctor` (corps trivial DEDUPLIQUE) alors que les trois classes
     derivent de `NonComparablePlaybook`1`. Meme piege que #487-r1 / #945.
  2. **`1140 ExemplarOfHate` lit `StatPart.CurrentPct`, pas `Current`.** `1164 MindControl` a la
     MEME forme apparente (`GetStat(target, 5, ...)`) et lit `Current`. Confondre les deux ne leve
     AUCUNE erreur et change l'ordre des cibles des que deux d'entre elles ont des `maxHp` distincts.
  3. **`0x7ea` n'est PAS un trait gameconfig** : c'est le pseudo-trait de GRANDE-ALLIANCE `Chaos`,
     derive du `GrandAllianceId`. Un `HasTrait` naif sur la liste `traits` rendrait TOUJOURS faux et
     la branche `+1` serait MORTE (meme piege que la face COMBAT, `darkangels.CHAOS_FACTIONS`).
  4. **`1115 FearOfTheUnseen` est un VETO sur l'UNION**, pas sur `fromHere` : le natif lit
     `ValidTargets.<+0x10>` = `GetAllValidTargetsFromAllPossibleMovementTiles`. Gater sur la seule
     position courante rendrait le veto BEAUCOUP trop permissif.
  5. **`1097 Foehammer` ne compte PAS ce que son ability utilise.** Le playbook compte
     `AllDeadUnits()` NU (les deux camps, aucun filtre) ; `...FoehammerAbility$$ExecuteBehaviour`
     compte, lui, `UnitsWithTrait(AllDeadOrResurrectedUnits(), Hero)`. Ecart NATIF, transcrit tel quel.
  6. **`1179 CultDemagogue` ancre `PossibleTilesForDecoys` sur `<DSLSelectors+0x60> = Target`**, pas
     sur le caster : le terme dominant de son utilite est donc PAR CIBLE et DEPARTAGE l'argmax. Le
     port le calculait une fois, hors boucle, depuis l'origine du caster.
  7. **Le splash de `1017 FragBomb` est `AdjacentUnits` NU** (friendly-fire), sans wrapper `Enemies`
     -- contraste `MassDriverAccelerator`, qui en a un.

Aucune valeur de gameplay n'est ecrite en dur : `nrOfHits`/`nrOfHits_2` sont re-derives du
gameconfig, les traits par leur membre d'enum. Seuls la STRUCTURE, les SEUILS lus au decompile et
les FERMETURES sont assertes.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe le registre `PLAYBOOKS` (donc tout
    # `engine.playbook.noncomparable`), `bespoke` (route Comparable BESPOKE), `active_ability`
    # (`_SPECIAL_ABILITY_CLASSES` + `_NONCOMPARABLE_ABILITIES`) et `playbook.prediction.abilities`.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire : les seuils (`1`, `10`) sont
    # ceux LUS au decompile, les magnitudes viennent du gameconfig.
    "build": False,
    # offline pur, aucun runner, < 2 s.
    "toujours": True,
    "raison": "Gardes OFFLINE des faces DECISION du 2e lot Loki (#957) : les trois bases "
              "NonComparable, le StatPart.CurrentPct d'ExemplarOfHate, le pseudo-trait "
              "d'alliance Chaos, le VETO sur l'UNION de FearOfTheUnseen, le comptage "
              "AllDeadUnits NU de Foehammer, l'ancre Target de CultDemagogue et le splash "
              "friendly-fire de FragBomb.",
}

import pytest

import gameconfig as GC

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.playbook.noncomparable import PLAYBOOKS
from engine.playbook.noncomparable._base import NCContext

FOEHAMMER = int(ActiveAbilityType.Foehammer)                 # 0x449 = 1097
FEAR = int(ActiveAbilityType.FearOfTheUnseen)                # 0x45b = 1115
EXEMPLAR = int(ActiveAbilityType.ExemplarOfHate)             # 0x474 = 1140
CULT = int(ActiveAbilityType.CultDemagogue)                  # 0x49b = 1179
FRAG = int(ActiveAbilityType.FragBomb)                       # 0x3f9 = 1017
EXCRU = int(ActiveAbilityType.ExcruciatingFrequencies)       # 0x4ad = 1197


def _ctx(**kw) -> NCContext:
    base = dict(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    base.update(kw)
    return NCContext(**base)


def _obs(sq, vid, pos=(0, 0), hp=100, hpmax=100, dead=False):
    return {"squadId": sq, "visualId": vid, "col": pos[0], "row": pos[1],
            "hp": hp, "hpMax": hpmax, "isDead": dead}


def _targets_stub(uid, ability_id, targets, cle="fromHere"):
    """Mirror minimal de l'RPC `abilityTargets`. `cle` selectionne la VUE publiee : `fromHere`
    (position courante) ou `targets` (l'UNION sur toutes les tuiles de move) -- la distinction est
    exactement le piege 4."""
    def _call(u, a):
        if u != uid or a != ability_id:
            return {}
        return {"units": [{"unitId": uid, "abilities": [
            {"abilityId": ability_id, cle: [{"targetId": t} for t in targets]}]}]}
    return _call


#: Trois visualId REELS, choisis pour leurs DRAPEAUX et verifies ci-dessous contre le gameconfig --
#: jamais supposes. `spaceHound` porte `Infiltrate` ; `blackAbaddon` est `Chaos` sans `Infiltrate` ;
#: `adeptCanoness` n'est ni l'un ni l'autre. Ce sont les trois cibles du montage LIVE de #957.
CIBLE_INFILTRATE = "spaceHound"
CIBLE_CHAOS = "blackAbaddon"
CIBLE_NEUTRE = "adeptCanoness"
#: Un porteur du trait `Object` -- la seule cible que 1140 ECARTE (`continue`). Les 28 porteurs du
#: build sont les `LootObj_*` (objets de butin posés sur le plateau) ; aucune unite jouable ne le
#: porte, ce qui est exactement pourquoi la branche est facile a oublier.
CIBLE_OBJET = "LootObj_AmmoBox"


def _cfg(vid):
    return GC.unit(GC.resolve_unit_id(vid) or vid) or {}


# =============================================================================================
# ETAGE 0 -- LE SUBSTRAT DES TEMOINS EST CE QUE JE CROIS (un test qui s'assertionne lui-meme)
# =============================================================================================
def test_les_temoins_portent_bien_les_drapeaux_qu_on_leur_prete():
    """Sans ce cran, les etages 2-3 pourraient passer sur des temoins DEGENERES (trois cibles aux
    memes drapeaux) et ne rien mesurer. Meme discipline que le « assertionner son propre non-vide »
    du CLAUDE.md."""
    assert UnitTrait.Infiltrate.name in (_cfg(CIBLE_INFILTRATE).get("traits") or ()), \
        "%s ne porte plus Infiltrate -- temoin a re-choisir" % CIBLE_INFILTRATE
    assert _cfg(CIBLE_INFILTRATE).get("GrandAllianceId") != "Chaos"
    assert UnitTrait.Infiltrate.name not in (_cfg(CIBLE_CHAOS).get("traits") or ())
    assert _cfg(CIBLE_CHAOS).get("GrandAllianceId") == "Chaos", \
        "%s n'est plus de grande-alliance Chaos -- temoin a re-choisir" % CIBLE_CHAOS
    assert UnitTrait.Infiltrate.name not in (_cfg(CIBLE_NEUTRE).get("traits") or ())
    assert _cfg(CIBLE_NEUTRE).get("GrandAllianceId") not in (None, "Chaos")
    assert UnitTrait.Object.name in (_cfg(CIBLE_OBJET).get("traits") or ()), \
        "%s ne porte plus Object -- temoin a re-choisir" % CIBLE_OBJET
    # Et le pseudo-trait `Chaos` n'est JAMAIS dans la liste `traits` du gameconfig (piege 3) : c'est
    # ce qui rend le detour par `GrandAllianceId` OBLIGATOIRE.
    assert UnitTrait.Chaos.name not in (_cfg(CIBLE_CHAOS).get("traits") or ()), \
        "Chaos serait un trait gameconfig -- la RE du piege 3 serait a refaire"


# =============================================================================================
# ETAGE 1 -- LES TROIS PLAYBOOKS SONT AU REGISTRE, AVEC LEUR SEUIL LU (piege 1)
# =============================================================================================
@pytest.mark.parametrize("aid,classe,seuil", [
    (FOEHAMMER, "FoehammerPlaybook", 1.0),
    (FEAR, "FearOfTheUnseenPlaybook", 1.0),
    (EXEMPLAR, "ExemplarOfHatePlaybook", 1.0),
])
def test_le_playbook_est_inscrit_avec_son_seuil(aid, classe, seuil):
    """Non inscrit => l'IA ne propose JAMAIS l'ability par cette voie (no-op silencieux). Les trois
    seuils viennent d'un `.cctor` PROPRE (`Fix64.op_Implicit(1)`), lu classe par classe."""
    assert aid in PLAYBOOKS, "%d absent de PLAYBOOKS" % aid
    pb = PLAYBOOKS[aid]
    assert type(pb).__name__ == classe
    assert pb.MIN_UTILITY == seuil
    assert pb.PRIORITY == 0, "1097/1115/1140 sont hors de NATIVE_PRIORITY (sweep #170)"


@pytest.mark.parametrize("nom", ["ExemplarOfHate", "FearOfTheUnseen", "Foehammer"])
def test_les_trois_sont_declarees_NON_comparables(nom):
    """Leurs classes natives n'ont AUCUN `Make*Predictions` (recensement AU BLOC d'adresses de
    `ghidra/functions.tsv` : trois corps CONTIGUS chacune). Le natif n'emet donc aucun
    `ProbableDamageEvent` -- sans cette entree, le port en fabriquerait un depuis leur
    `minDmg`/`maxDmg` gameconfig. CONFIRME LIVE : `decisionView.attackPlans` rend `[0-0]` pour
    1140 comme pour 1097 (montage `darkaAsmodai`+`spaceRockfist`, board MC1_67)."""
    from engine.entities.abilities.active_ability import makes_damage_predictions
    assert makes_damage_predictions(nom) is False, "%s doit etre NonComparable" % nom


def test_foehammer_est_une_attaque_et_reste_NonComparable():
    """Cran ANTI-SIMPLIFICATION : `1097` EST une attaque (sa face COMBAT fait un
    `AttackWithAttackDamage`), et pourtant son PLAYBOOK est NonComparable. Un lecteur qui
    « corrigerait » l'entree en la croyant erronee re-ouvrirait la sur-prediction."""
    assert (_cfg("spaceRockfist").get("activeAbilities") or []), "porteur introuvable"
    cfg = GC.ability("Foehammer") or {}
    assert (cfg.get("variables") or {}).get("minDmg") is not None \
        or (cfg.get("constants") or {}).get("nrOfHits") is not None, \
        "1097 n'a plus de profil de degat -- la premisse du cran a change"


# =============================================================================================
# ETAGE 2 -- `1140 ExemplarOfHate` : la formule, terme par terme (pieges 2 et 3)
# =============================================================================================
def _u_exemplar(vid, hp=100, hpmax=100):
    pb = PLAYBOOKS[EXEMPLAR]
    ctx = _ctx(obs_units=[_obs(7, vid, hp=hp, hpmax=hpmax)])
    return pb.evaluate_non_comparable((0, 0), 7, ctx)


def test_exemplar_ecarte_la_cible_Object():
    """`if (HasTrait(t, 0xd = Object)) continue` -- AUCUNE action pour elle, pas une utilite basse."""
    assert _u_exemplar(CIBLE_OBJET) is None


def test_exemplar_les_trois_paliers_de_drapeaux():
    """`1 + PV%/100 + 2*(NON Infiltrate) + 1*(Chaos)`. A PV pleins : 2.0 / 4.0 / 5.0 ... non :
    `Infiltrate` = 1 + 1 = 2 ; neutre = 1 + 1 + 2 = 4 ; Chaos = 1 + 1 + 2 + 1 = 5. L'ORDRE est ce
    que le natif exerce, et c'est lui que le montage live a fait basculer."""
    u_inf = _u_exemplar(CIBLE_INFILTRATE)
    u_neutre = _u_exemplar(CIBLE_NEUTRE)
    u_chaos = _u_exemplar(CIBLE_CHAOS)
    assert u_inf == pytest.approx(2.0)
    assert u_neutre == pytest.approx(4.0)
    assert u_chaos == pytest.approx(5.0)
    assert u_chaos > u_neutre > u_inf, "l'ordre des cibles est le seul observable du playbook"


def test_exemplar_lit_le_POURCENTAGE_de_pv_pas_les_pv_bruts():
    """Piege 2. Deux cibles au MEME pourcentage mais aux `maxHp` opposes doivent avoir la MEME
    utilite ; un port qui lirait `StatPart.Current` les separerait de plusieurs milliers."""
    a = _u_exemplar(CIBLE_NEUTRE, hp=500, hpmax=1000)
    b = _u_exemplar(CIBLE_NEUTRE, hp=5000, hpmax=10000)
    assert a == pytest.approx(b)
    assert a == pytest.approx(4.0 - 0.5), "50 %% de PV -> terme 0.5, pas 500"


def test_exemplar_ligne_obs_absente_vaut_pleine_vie():
    """`hp`/`hpMax` non mesures -> 100 %% (le defaut de `BloodChalicePlaybook`), jamais 0 : un 0
    fabrique depuis une NON-MESURE deplacerait l'argmax.

    Le reste de la formule prend alors ses defauts d'ABSENCE de trait : pas d'`Object` (donc pas de
    `continue`), pas d'`Infiltrate` (donc `+2`), pas de `Chaos` (donc pas de `+1`) -- soit
    `1 + 1.0 + 2 = 4.0`. C'est le MEME palier que la cible neutre a PV pleins, et c'est voulu :
    l'inconnu ne doit pas etre PENALISE."""
    pb = PLAYBOOKS[EXEMPLAR]
    u = pb.evaluate_non_comparable((0, 0), 7, _ctx(obs_units=[]))
    assert u == pytest.approx(4.0)
    assert u == pytest.approx(_u_exemplar(CIBLE_NEUTRE)), \
        "le terme PV d'une ligne absente doit valoir 100 %%, pas 0"


def test_exemplar_choisit_la_cible_de_plus_haute_utilite_et_ne_bouge_pas():
    """Le generateur complet : enumeration `fromHere`, argmax STRICT, `to = None` (l'eligibilite
    ET l'utilite sont position-INDEPENDANTES sur `useWholeBoard`)."""
    pb = PLAYBOOKS[EXEMPLAR]
    ctx = _ctx(obs_units=[_obs(11, CIBLE_INFILTRATE), _obs(12, CIBLE_CHAOS), _obs(13, CIBLE_NEUTRE)],
               ability_targets=_targets_stub(1, EXEMPLAR, [11, 12, 13]))
    out = pb.generate_candidates(ctx)
    assert len(out) == 1
    assert out[0]["ability"] == EXEMPLAR
    assert out[0]["target"] == 12, "la cible Chaos non-Infiltrate domine (5.0)"
    assert out[0]["to"] is None


def test_exemplar_garde_la_PREMIERE_cible_a_utilite_EGALE():
    """`Bucket$$AddAction` SEED le 1er ajoute puis ne remplace que si STRICTEMENT superieur : deux
    cibles au MEME palier se departagent par l'ORDRE d'enumeration du selecteur, pas par la
    derniere vue. Un `>=` au lieu du `>` inverserait ce tie sans rien changer d'autre."""
    pb = PLAYBOOKS[EXEMPLAR]
    ctx = _ctx(obs_units=[_obs(21, CIBLE_NEUTRE), _obs(22, CIBLE_NEUTRE)],
               ability_targets=_targets_stub(1, EXEMPLAR, [21, 22]))
    assert pb.evaluate_non_comparable((0, 0), 21, ctx) == \
        pb.evaluate_non_comparable((0, 0), 22, ctx), "temoin DEGENERE : les deux ne sont pas a egalite"
    assert pb.generate_candidates(ctx)[0]["target"] == 21


def test_exemplar_sans_rpc_ne_propose_rien():
    assert PLAYBOOKS[EXEMPLAR].generate_candidates(_ctx()) == []


# =============================================================================================
# ETAGE 3 -- `1115 FearOfTheUnseen` : le VETO porte sur l'UNION (piege 4)
# =============================================================================================
def _ctx_fear(union, from_here=()):
    """Le caster porte l'attaque normale `69` (`ctx.units`), et l'RPC publie les DEUX vues :
    `targets` = l'UNION sur toutes les tuiles de move (ce que le natif lit), `fromHere` = la seule
    position courante (ce qu'un port distrait lirait)."""
    def _call(u, a):
        if u != 1 or a != 69:
            return {}
        return {"units": [{"unitId": 1, "abilities": [{
            "abilityId": 69,
            "targets": [{"targetId": t} for t in union],
            "fromHere": [{"targetId": t} for t in from_here]}]}]}
    return _ctx(units=[{"id": 1, "abilities": [{"id": 69, "kind": "normal"}]}],
                ability_targets=_call)


def test_fear_emet_sur_SOI_quand_l_union_est_vide():
    out = PLAYBOOKS[FEAR].generate_candidates(_ctx_fear([]))
    assert len(out) == 1
    assert out[0] == {"target": 1, "ability": FEAR, "to": None, "pred": 10.0}


def test_fear_se_tait_des_qu_une_cible_existe_dans_l_UNION():
    assert PLAYBOOKS[FEAR].generate_candidates(_ctx_fear([42])) == []


def test_fear_ne_lit_PAS_fromHere():
    """Piege 4, dans le SEUL regime qui separe les deux lectures : une cible atteignable APRES
    deplacement (`targets` non vide) mais PAS depuis la position courante (`fromHere` vide). Le
    natif ne se teleporte pas ; un port branche sur `fromHere` verrait `[]` et emettrait a tort."""
    ctx = _ctx_fear([42], from_here=())
    assert PLAYBOOKS[FEAR].generate_candidates(ctx) == [], \
        "le veto doit porter sur l'UNION (`ValidTargets.<+0x10>`), pas sur la position courante"


def test_fear_sans_mesure_s_abstient():
    """`ability_targets` absent, ou aucune attaque normale connue : le veto natif est une condition
    POSITIVE, la fabriquer depuis une NON-MESURE proposerait un teleport que le natif ne fait pas."""
    assert PLAYBOOKS[FEAR].generate_candidates(_ctx()) == []
    ctx = _ctx(units=[{"id": 1, "abilities": []}], ability_targets=_targets_stub(1, 69, []))
    assert PLAYBOOKS[FEAR].generate_candidates(ctx) == []


# =============================================================================================
# ETAGE 4 -- `1097 Foehammer` : `AllDeadUnits()` NU, et le gate qui en decoule (piege 5)
# =============================================================================================
def _plan_foehammer(cibles):
    return {"evals": [{"abilityId": FOEHAMMER, "targetId": t, "rankCount": 1,
                       "ranked": [{"col": 0, "row": 0}]} for t in cibles]}


def test_foehammer_compte_les_morts_des_DEUX_camps_sans_filtre():
    """Le playbook lit `GetAllDeadUnits(playerEntityId: null)` : aucun filtre de proprietaire, et
    surtout AUCUN filtre `Hero` (contraste `...FoehammerAbility$$ExecuteBehaviour`, piege 5)."""
    pb = PLAYBOOKS[FOEHAMMER]
    ctx = _ctx(obs_units=[_obs(11, CIBLE_NEUTRE, dead=True),      # un HERO mort
                          _obs(12, CIBLE_OBJET, dead=True),       # un SUMMON/objet mort
                          _obs(13, CIBLE_CHAOS, dead=False)])
    assert pb.evaluate_non_comparable((0, 0), 99, ctx) == pytest.approx(2.0)


def test_foehammer_est_muet_tant_qu_aucune_unite_n_est_morte():
    """`MIN_UTILITY = 1` sur une utilite qui vaut le NOMBRE de morts : avant la premiere mort le
    tier NonComparable ne propose rien, et le fallback Comparable reprend la main."""
    pb = PLAYBOOKS[FOEHAMMER]
    ctx = _ctx(obs_units=[_obs(13, CIBLE_CHAOS)], plan=_plan_foehammer([13]),
               reach_nc=[(0, 0)])
    assert pb.evaluate_non_comparable((0, 0), 13, ctx) == pytest.approx(0.0)
    assert pb.generate_candidates(ctx) == []


def test_foehammer_propose_des_le_premier_mort_et_reste_en_place():
    """Utilite CONSTANTE => `Bucket$$AddAction` (remplacement STRICT) garde le PREMIER couple
    (position, cible) : l'ORIGINE, et la premiere cible du plan."""
    pb = PLAYBOOKS[FOEHAMMER]
    ctx = _ctx(obs_units=[_obs(11, CIBLE_NEUTRE, dead=True), _obs(13, CIBLE_CHAOS)],
               plan=_plan_foehammer([13, 14]), reach_nc=[(0, 0)])
    out = pb.generate_candidates(ctx)
    assert len(out) == 1
    assert out[0]["ability"] == FOEHAMMER and out[0]["to"] is None
    assert out[0]["target"] == 13, "utilite constante -> la 1re cible enumeree gagne"
    assert out[0]["pred"] == pytest.approx(1.0)


# =============================================================================================
# ETAGE 5 -- `1179 CultDemagogue` : l'ancre est la CIBLE (piege 6)
# =============================================================================================
def test_cult_demagogue_ancre_ses_tuiles_libres_sur_la_CIBLE():
    """`PossibleTilesForDecoys` = `CanAddUnit(SurroundingTiles(<DSLSelectors+0x60> = Target, ...))`.

    Deux cibles au MEME voisinage d'alliés-summons mais aux voisinages LIBRES differents doivent
    donner des utilites differentes. Un port ancre sur le CASTER rendrait la MEME valeur pour les
    deux -- et l'argmax serait alors decide par le seul terme 2 (souvent nul)."""
    import hexgeo
    from engine.playbook.bespoke import CultDemagoguePlaybook
    pb = CultDemagoguePlaybook()

    # La carte MARCHABLE est CALIBREE sur `nrOfSummons` : le terme natif est
    # `min(|tuiles libres|, nrOfSummons)`, donc deux cibles au-DESSUS du plafond seraient a EGALITE
    # et le test ne mesurerait rien. On met donc la cible du COIN sous le plafond (2 tuiles) et
    # celle du large au-dessus (le disque r2 complet).
    _decoy_amt = 4
    _large = {t for t in ((c, r) for c in range(0, 8) for r in range(0, 8))
              if hexgeo.distance((5, 5), t) <= 2}
    _coin = {(0, 0), (0, 1), (1, 1), (0, 2)}     # 2 tuiles LIBRES a <=2 de (0,1) : (1,1) et (0,2)
    _walk = {t: True for t in (_large | _coin)}

    class _Ctx:
        uid = 1
        origin = (0, 0)
        epos = [(5, 5), (0, 1)]
        fpos = []
        debug = False
        # `walkable_by_pos` : (5,5) est AU LARGE (disque r2 entier marchable), (0,1) est ENFERME
        # (deux tuiles libres seulement). C'est la carte que `can_add_unit` consomme.
        walkable_by_pos = _walk
        units = [{"id": 1, "team": 1, "alive": True, "pos": {"col": 0, "row": 0}},
                 {"id": 11, "team": 2, "alive": True, "pos": {"col": 5, "row": 5}},
                 {"id": 12, "team": 2, "alive": True, "pos": {"col": 0, "row": 1}}]
        me = units[0]

        @staticmethod
        def heal_config(_uid):
            return {"active": 1, "passive": 1, "multiplier": 100}

        class wt:
            @staticmethod
            def sub(_cat, _key):
                return 20.0

        @staticmethod
        def ability_targets(u, a):
            if u != 1 or a != CULT:
                return {}
            # ⚠ ORDRE VOLONTAIRE : la cible du COIN (12) est enumeree EN PREMIER. C'est ce qui
            # separe les deux lectures -- ancre CASTER => les deux cibles ont le MEME terme 1, donc
            # egalite, donc `AddAction` garde la PREMIERE (12) ; ancre CIBLE => 11 (au large) gagne
            # strictement. Avec l'ordre inverse, les deux lectures rendraient 11 et la mutation
            # serait MUETTE (mesure : elle l'etait).
            return {"units": [{"unitId": 1, "abilities": [{"abilityId": CULT, "targets": [
                {"kind": "unit", "targetId": 12}, {"kind": "unit", "targetId": 11}]}]}]}

    n_large = pb._free_tiles_around(_Ctx, (5, 5))
    n_coin = pb._free_tiles_around(_Ctx, (0, 1))
    n_caster = pb._free_tiles_around(_Ctx, _Ctx.origin)
    assert min(n_large, _decoy_amt) > min(n_coin, _decoy_amt), \
        "temoin DEGENERE : les deux cibles rendent le meme terme 1 (plafond `nrOfSummons` atteint " \
        "des deux cotes) -- le test ne separerait pas les deux ancres"
    assert min(n_caster, _decoy_amt) == min(n_caster, _decoy_amt), "(lecture, pas assertion)"
    out = pb.generate_candidates(_Ctx)
    assert len(out) == 1 and out[0]["ability"] == CULT
    assert out[0]["target"] == 11, \
        "l'argmax doit suivre le voisinage libre de la CIBLE (11 est au large, 12 dans un coin)"


def test_cult_demagogue_exclut_le_centre_et_compte_le_caster_comme_occupant():
    """`includeCenter = 0` (2e argument du `SurroundingTiles` natif, LU au call-site) ; et l'origine
    du caster est occupee bien qu'absente de `fpos` (qui exclut le mover)."""
    from engine.playbook.bespoke import CultDemagoguePlaybook
    pb = CultDemagoguePlaybook()

    class _Ctx:
        uid = 1
        origin = (2, 2)
        epos = [(3, 3)]
        fpos = []
        walkable_by_pos = {(c, r): True for c in range(0, 6) for r in range(0, 6)}

    libres = pb._free_tiles_around(_Ctx, (3, 3))
    import hexgeo
    disque = [t for t in _Ctx.walkable_by_pos
              if t != (3, 3) and hexgeo.distance((3, 3), t) <= pb._RANGE]
    # centre exclu (deja garanti par `t != center`), + la tuile de la cible et celle du caster
    # retirees par `can_add_unit` des qu'elles sont dans le disque.
    assert libres == len([t for t in disque if t not in ((2, 2), (3, 3))])


# =============================================================================================
# ETAGE 6 -- `1017 FragBomb` : le splash est `AdjacentUnits` NU (piege 7)
# =============================================================================================
def test_frag_bomb_a_sa_classe_de_prediction_et_son_handler():
    from engine.entities.abilities.active_ability import _SPECIAL_ABILITY_CLASSES
    from engine.playbook.prediction.abilities import _MAKE_DMG_INPUT_OVERRIDES
    assert _SPECIAL_ABILITY_CLASSES.get("FragBomb") is not None, \
        "sans classe, `get_aoe_targets` rend [] et le SPLASH n'est jamais predit"
    assert FRAG in _MAKE_DMG_INPUT_OVERRIDES, \
        "sans handler, le splash heriterait des coups du batch PRINCIPAL"


def test_frag_bomb_les_deux_comptes_de_coups_viennent_du_gameconfig():
    """`GetHits` = `GetNumberConstant(0x2f = nrOfHits)` LITTERAL (le generique ajouterait `ExtraHits`)
    et `GetHits2` = `GetNumberConstant(0x32 = nrOfHits_2)` pour le splash. La BASE n'est PAS
    surchargee : elle est HERITEE (le `param_6` du natif est evalue UNE fois, hors boucle)."""
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.playbook.prediction.abilities import _frag_bomb_inputs
    cfg = AbilityConfiguration.from_gameconfig("FragBomb", GC.ability("FragBomb"))
    out = _frag_bomb_inputs(None, None, None, None, cfg)
    consts = cfg.constants or {}
    assert out["hits_override"] == int(consts["nrOfHits"])
    assert out["aoe_overrides"] == {"hits_override": int(consts["nrOfHits_2"])}
    assert "base_override" not in out and "base_override" not in out["aoe_overrides"], \
        "la base du splash est HERITEE du batch principal (param_6 partage)"
    assert int(consts["nrOfHits"]) != int(consts["nrOfHits_2"]), \
        "temoin DEGENERE : les deux comptes de coups sont egaux, le volet ne s'observe pas"


def test_frag_bomb_le_splash_n_a_PAS_de_filtre_ennemi():
    """Piege 7 : `AdjacentUnits` NU moins le caster -- les ALLIES adjacents a la tuile ciblee sont
    predits (leur event est `friendly`, donc son utilite est NEGEE). Contraste
    `MassDriverAcceleratorAbility`, dont le set passe par `AdjacentEnemies`."""
    from engine.entities.abilities.active_ability import (FragBombAbility,
                                                          MassDriverAcceleratorAbility)
    assert type(FragBombAbility._AOE).__name__ == "Sub", \
        "le set doit etre une SOUSTRACTION (`... op_Subtraction Caster`)"
    assert type(FragBombAbility._AOE.a).__name__ == "AdjacentUnits", \
        "un `AdjacentEnemies` ici supprimerait le friendly-fire mesure live cote COMBAT"
    assert type(MassDriverAcceleratorAbility._AOE).__name__ == "AdjacentEnemies", \
        "temoin de contraste : 1222 a bien un filtre ennemi, 1017 non"


# =============================================================================================
# ETAGE 7 -- VERDICTS VERROUILLES : ce qui etait DEJA porte ne doit pas etre RE-porte
# =============================================================================================
def test_excruciating_frequencies_garde_sa_route_BESPOKE():
    """`1197` n'est PAS un NonComparable et n'entre PAS au registre Comparable : sa route est le
    generateur bespoke `playbook/excruciating_frequencies.py`, et son gate le seuil statique
    `Fix64(10)`. L'inscrire ailleurs serait un port MORT qui masquerait ou vit son gate."""
    from engine.playbook.base import REGISTRY
    from engine.playbook.static_threshold_gate import NOT_REGISTERED, STATIC_UTILITY_THRESHOLD
    from engine.playbook.excruciating_frequencies import _ABILITY_ID
    assert EXCRU not in PLAYBOOKS, "1197 est COMPARABLE (MakeDamagePredictions + ShouldExecute)"
    assert EXCRU not in REGISTRY
    assert EXCRU in NOT_REGISTERED
    assert int(_ABILITY_ID) == EXCRU
    assert STATIC_UTILITY_THRESHOLD == 10.0


def test_cult_demagogue_garde_sa_route_BESPOKE():
    """`1179` surcharge `EvaluateInternal` en ENTIER (aucun `MakeDamagePredictions`) : sa route est
    `BESPOKE_SELFCAST`, pas le registre NonComparable."""
    from engine.playbook.base import REGISTRY
    from engine.playbook.bespoke import BESPOKE_SELFCAST
    assert CULT in BESPOKE_SELFCAST
    assert CULT not in PLAYBOOKS and CULT not in REGISTRY


# =============================================================================================
# ETAGE 8 -- LE ROUGE DE `master` QUE CETTE TRANCHE A REVELE (hors sujet #957, mais bloquant)
# =============================================================================================
def test_scene_enmity_adjacent_ne_leve_pas_sur_un_voisin_vivant():
    """`Scene._enmity_adjacent` appelait `self.traits(oid)` -- methode qui n'existe QUE sur
    `_SceneEffectTargetWorld`, pas sur `Scene`. Le corps levait donc `AttributeError` DES QU'UNE
    unite vivante etait hex-adjacente au porteur (rouge introduit par #947+#948, latent parce que
    la boucle sort AVANT sur un board ou personne n'est au contact). Il est sur le chemin
    INCONDITIONNEL de `make_normal_attack_predictions`, donc il tombait a chaque prediction
    d'attaque normale au contact -- c'est ce qui a bloque la validation live de #957.

    Le canal correct est `ctx_by_id[<uid>].traits`, deja publie en NOMS."""
    from engine.playbook.scene import Scene

    class _UCtx:
        traits = ()

    sc = Scene(ctx_by_id={1: _UCtx(), 2: _UCtx()}, armor_by_id={}, shield_by_id={},
               mult_by_id={}, ablvl_by_id={}, vis_by_id={},
               units=[{"id": 1, "alive": True, "team": 1},
                      {"id": 2, "alive": True, "team": 1}],
               hp_by_id={1: 10, 2: 10}, pos_by_id={1: (0, 0), 2: (1, 0)},
               team_by_id={1: 1, 2: 1}, eff_state=None)
    assert sc.enmity_adjacent_units(1) == 1, "un voisin vivant sans trait bloquant doit compter"

    class _Objet:
        traits = (UnitTrait.Object.name,)

    sc.ctx_by_id[2] = _Objet()
    assert sc.enmity_adjacent_units(1) == 0, \
        "`NonSteppableOrObjectUnits` retire l'Object -- le filtre doit rester exerce"
