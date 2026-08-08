"""CLIQUET #498-r1 -- face DECISION de `1152 UnstoppableMomentumReworked`.

`IdunBattle.AI.Playbook.Loki.UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable` compte les
ennemis que la charge va TRAVERSER, le long de la ligne rendue par
`UnstoppableMomentumReworkedAbility$$GetAllTilesInLine`, en s'ARRETANT a la premiere tuile ou
`$$CanContinue` refuse.

Ce fichier garde les TROIS lectures que ni `case-498` §4-§5 ni le backlog ne portaient, et dont
aucune n'est visible d'un test qui ne regarderait que « l'ability est-elle proposee » :

  1. **`MIN_UTILITY` DYNAMIQUE, a deux valeurs.** Le `.cctor` ecrit `Fix64(2)` ET `Fix64(1)` ; la
     leaf choisit par `IdunBattle.AI.Playbook.BasePlaybook$$EnemyCouldBeDamagedWithNormalAttack`
     (= `GetAllNormalAttackTargets(caster).Count > 0`, `IBattleQuery` slot **0x45** =
     `GetAllValidTargetsFromAllPossibleMovementTiles`, donc l'UNION sur les tuiles de move, PAS
     `HasValidTargets` depuis la position courante). Un seuil scalaire serait faux dans UN des deux
     regimes -- et vert dans l'autre.
  2. **Le `break` fait un PREFIXE.** Les ennemis situes DERRIERE une tuile refusee ne comptent pas.
     Un `continue` a la place donnerait la meme valeur sur toute geometrie sans blocage : seul un
     montage AVEC blocage intermediaire separe les deux.
  3. **La ligne part de la POSITION CANDIDATE**, pas de la tuile reelle du caster -- LU dans
     `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` (surcharge 3 args), qui
     ecrit `AbilityEntities+0x40 casterTile = possibleCasterTile`.

Ce que le cliquet mord (mutations verifiees ROUGE avant vert) :
  * seuil fige a 1 (ou a 2)                          -> test_seuil_dynamique_deux_valeurs
  * `break` remplace par `continue`                  -> test_le_break_est_un_prefixe
  * compter les ALLIES traverses                     -> test_seuls_les_ennemis_comptent
  * ligne tracee depuis l'origine au lieu de la tuile balayee -> test_ligne_depuis_la_position

100 % OFFLINE : aucun runner, aucun RPC. ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]          # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.playbook import noncomparable as NC                      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType    # noqa: E402

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
#: `engine/**` en glob : l'import du registre NonComparable traine tout le paquet, et l'utilite
#: passe par `battle_query.get_tiles_behind` + `runner.components.NOT_DISPLACEABLE_TRAITS`, deux
#: foyers PARTAGES qu'une liste nommee laisserait filer.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : le contexte et les positions sont construits a la main, aucun "
              "runner ni RPC, et aucune table du build n'est lue (la hierarchie du playbook est "
              "gardee cote #487-r1, qui lit `classes.tsv`).",
}

ABILITY = int(ActiveAbilityType.UnstoppableMomentumReworked)     # 0x480 = 1152


def _ctx(units, caster_pos, targets, *, normal_targets=(), walkable=None, uid=1, reach=None):
    """`NCContext` minimal. `normal_targets` non vide -> `EnemyCouldBeDamagedWithNormalAttack`."""
    NORMAL = 69

    def _ability_targets(u, aid):
        if u != uid:
            return {"units": []}
        if aid == ABILITY:
            lst = [{"kind": "unit", "targetId": t} for t in targets]
            return {"units": [{"unitId": uid, "abilities": [
                {"abilityId": ABILITY, "fromHere": lst, "targets": lst}]}]}
        if aid == NORMAL:
            lst = [{"kind": "unit", "targetId": t} for t in normal_targets]
            return {"units": [{"unitId": uid, "abilities": [
                {"abilityId": NORMAL, "fromHere": [], "targets": lst}]}]}
        return {"units": []}

    me = {"id": uid, "abilities": [{"id": NORMAL, "kind": "normal"}]}
    all_units = [me if u.get("id") == uid else u for u in units]
    for u in all_units:                      # l'unite qui decide porte son attaque normale
        if u.get("id") == uid:
            u.setdefault("abilities", [{"id": NORMAL, "kind": "normal"}])
    return NC.NCContext(uid=uid, origin=caster_pos, reach_nc=(reach or [caster_pos]), epos=[],
                        fpos=[], plan={}, hp_cur_by_id={}, ability_targets=_ability_targets,
                        units=all_units, walkable_by_pos=(walkable or {}))


def _u(uid, col, row, ctrl, visual="orksNob"):
    return {"id": uid, "pos": {"col": col, "row": row}, "ctrl": ctrl, "alive": True,
            "visualId": visual, "abilities": []}


def _grille(cols=8, rows=8, sauf=()):
    """Toutes les tuiles marchables, sauf celles listees (mur / non placable)."""
    return {(c, r): ((c, r) not in sauf) for c in range(cols) for r in range(rows)}


# La geometrie est HEX (odd-q) : une « ligne droite » n'est PAS une suite de colonnes. La ligne
# native depuis `CASTER_POS` vers `(2,0)` est MESUREE (`battle_query.get_tiles_behind`, apres le pas
# unitaire de `DirectionTo`) et commence par `[(2,0), (3,1), (4,1), ...]` ; dans l'autre sens,
# depuis `(3,0)` vers `(2,0)`, elle vaut `[(2,0), (1,1), (0,1)]`. Les montages ci-dessous s'appuient
# sur CES tuiles-la, jamais sur une intuition de grille carree.
CASTER_POS = (1, 0)
LIGNE = [(2, 0), (3, 1), (4, 1)]


def _caster():
    return {"id": 1, "pos": {"col": CASTER_POS[0], "row": CASTER_POS[1]}, "ctrl": True,
            "alive": True, "visualId": "spaceHound", "abilities": []}


# ------------------------------------------------------------------------------------------------
def test_inscrit_au_registre_noncomparable():
    pb = NC.PLAYBOOKS.get(ABILITY)
    assert pb is not None, "1152 absent de `noncomparable.PLAYBOOKS` : face DECISION non routee"
    assert type(pb).__name__ == "UnstoppableMomentumReworkedPlaybook"
    assert ABILITY not in NC.NATIVE_PRIORITY and pb.PRIORITY == 0


def test_seuil_dynamique_deux_valeurs():
    """`.cctor` = {Fix64(2), Fix64(1)} ; le choix vient d'`EnemyCouldBeDamagedWithNormalAttack`.

    Le montage est le MEME des deux cotes -- UN seul ennemi traverse, donc utilite 1. Il sort quand
    le caster n'a pas de cible a l'attaque normale (seuil 1) et PAS quand il en a une (seuil 2) :
    c'est exactement la difference qu'un seuil scalaire effacerait."""
    pb = NC.PLAYBOOKS[ABILITY]
    units = [{"id": 1, "pos": {"col": 0, "row": 0}, "ctrl": True, "alive": True,
              "visualId": "spaceHound", "abilities": []}, _u(10, 1, 0, False)]
    wk = _grille()
    sans = _ctx(units, (0, 0), [10], normal_targets=(), walkable=wk)
    avec = _ctx(units, (0, 0), [10], normal_targets=(10,), walkable=wk)
    assert pb.min_utility_for(sans) == 1.0
    assert pb.min_utility_for(avec) == 2.0
    cand_sans = pb.generate_candidates(sans)
    cand_avec = pb.generate_candidates(avec)
    assert len(cand_sans) == 1 and cand_sans[0]["pred"] == 1.0, cand_sans
    assert cand_avec == [], cand_avec        # 1 ennemi traverse < seuil 2


def test_seuls_les_ennemis_comptent():
    """`unit != null && !IsFriend(unit, caster)` : un ALLIE sur la ligne ne compte pas.

    Il ne BLOQUE pas non plus, tant qu'il est deplacable (`CanContinue` = `CanBeDisplaced | ...`)."""
    pb = NC.PLAYBOOKS[ABILITY]
    allie = _u(2, *LIGNE[0], True, "bloodIntercessor")           # ALLIE sur la ligne
    e1, e2 = _u(10, *LIGNE[1], False), _u(11, *LIGNE[2], False)
    ctx = _ctx([_caster(), allie, e1, e2], CASTER_POS, [10], walkable=_grille())
    occ = {LIGNE[0]: allie, LIGNE[1]: e1, LIGNE[2]: e2}
    assert pb._utility(ctx, CASTER_POS, LIGNE[0], occ) == 2.0


def test_le_break_est_un_prefixe():
    """Une tuile ou `CanContinue` refuse ARRETE le compte : ce qui est derriere ne compte pas.

    Le bloqueur est un ennemi a trait bloquant (`orksWarboss` -- `NOT_DISPLACEABLE_TRAITS`) :
    `CanBeDisplaced` est faux, et la tuile etant OCCUPEE le volet `IsCanAddUnit` ne la rattrape pas.
    TEMOIN NON NUL : le MEME montage avec un bloqueur ORDINAIRE (`orksNob`) rend 3."""
    pb = NC.PLAYBOOKS[ABILITY]
    derriere = [_u(11, *LIGNE[1], False), _u(12, *LIGNE[2], False)]
    wk = _grille()

    bloqueur = _u(10, *LIGNE[0], False, "orksWarboss")        # trait bloquant
    occ = {LIGNE[0]: bloqueur, LIGNE[1]: derriere[0], LIGNE[2]: derriere[1]}
    ctx = _ctx([_caster(), bloqueur] + derriere, CASTER_POS, [10], walkable=wk)
    bloque = pb._utility(ctx, CASTER_POS, LIGNE[0], occ)

    ordinaire = _u(10, *LIGNE[0], False)                      # orksNob : deplacable
    occ2 = dict(occ)
    occ2[LIGNE[0]] = ordinaire
    ctx2 = _ctx([_caster(), ordinaire] + derriere, CASTER_POS, [10], walkable=wk)
    libre = pb._utility(ctx2, CASTER_POS, LIGNE[0], occ2)

    assert libre == 3.0, libre        # TEMOIN NON NUL : sans blocage on traverse les trois
    assert bloque == 0.0, bloque      # le bloqueur lui-meme n'est pas franchi -> il ne compte pas


def test_ligne_depuis_la_position():
    """`AbilityEntities+0x40 casterTile = possibleCasterTile` : la ligne est re-tracee DEPUIS chaque
    position balayee. Si le port figeait l'origine, la valeur serait la MEME partout."""
    pb = NC.PLAYBOOKS[ABILITY]
    e1, e2 = _u(10, *LIGNE[0], False), _u(11, *LIGNE[1], False)
    occ = {LIGNE[0]: e1, LIGNE[1]: e2}
    ctx = _ctx([_caster(), e1, e2], CASTER_POS, [10], walkable=_grille(),
               reach=[CASTER_POS, (3, 0)])
    depuis_origine = pb._utility(ctx, CASTER_POS, LIGNE[0], occ)   # ligne (2,0),(3,1),(4,1)... -> 2
    depuis_autre = pb._utility(ctx, (3, 0), LIGNE[0], occ)         # ligne (2,0),(1,1),(0,1)   -> 1
    assert depuis_origine == 2.0, depuis_origine
    assert depuis_autre == 1.0, depuis_autre


def test_seuil_sans_canal_est_la_borne_basse():
    """`ability_targets` absent -> `EnemyCouldBeDamaged...` rend False -> seuil 1, jamais 2.

    Un canal muet ne doit pas RESSERRER le gate : c'est la meme convention que partout."""
    pb = NC.PLAYBOOKS[ABILITY]
    ctx = NC.NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                       hp_cur_by_id={}, ability_targets=None, units=[])
    assert pb.min_utility_for(ctx) == pb.MIN_UTILITY_WITHOUT_ATTACK == 1.0
    assert pb.generate_candidates(ctx) == []      # ... et sans cibles, aucun candidat
