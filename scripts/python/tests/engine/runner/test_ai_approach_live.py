"""#348 -- l'APPROCHE d'un acteur de free-attack, confrontee au LIVE.

CE QUE CES TESTS VERROUILLENT. Le corps unique
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` passe le `Nullable<int>` de
`behaviour+0x78` TEL QUEL a `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit,
ignoreFlags: true, overrideRange)` : `0` (`Direct(0)`, noeud `...FromCurrentPosition`) => la tuile
COURANTE seule ; `null` (noeud `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack`) => la plage
de deplacement NORMALE, donc l'acteur peut S'APPROCHER. `allowMoveAction` (`+0x70`) ajoute en queue
le `MovementActionGenerator`. Les messages sont appliques par
`IdunBattle.Core.Services.AiControl$$ApplyAiMessages` dans l'ordre `MoveUnitMessage` puis
`ActiveAbilityMessage` -- l'attaque part donc de la tuile FINALE.

Le port forcait `max_distance = 0` dans les DEUX branches et n'appliquait AUCUN deplacement : un
acteur hors portee ne faisait RIEN la ou le natif l'aurait fait avancer.

MONTAGE (`ai_approach_case`, porte de `scripts/python/probe_348_ai_approach.py`) : `ForwardSpotter`
(1143, MoW `astraOrdnanceBattery`) -- son on-appearance EST ce noeud, et son masque `0x40000422`
porte `TargetIsFriendly`, si bien que le guardsman nait sur une tuile libre adjacente a un ALLIE
CHOISI. On pose donc la distance spawn<->ennemi au hex pres. Guardsman : Movement 3, arme Las
portee 2 -> portee EFFECTIVE 5.

TROIS regimes, qui ne se recouvrent pas :
  * `approach`  d(spawn, ennemi) = 3..5 -> le natif AVANCE puis FRAPPE ;
  * `stay`      d(spawn, ennemi) <= 2   -> il FRAPPE SANS BOUGER (bras symetrique : sans lui on ne
                mesure que « il bouge », pas « il bouge quand il faut ») ;
  * `move_only` d(spawn, ennemi) >= 6   -> DEPLACEMENT PUR, aucun degat.

ASCII only (console cp1252).
"""
from __future__ import annotations


def test_the_actor_approaches_then_attacks(ai_approach_case):
    """REGIME `approach` -- l'acteur est HORS PORTEE depuis sa tuile de naissance mais A PORTEE
    apres deplacement.

    Cinq assertions qui ne se recouvrent pas :
      1. le cast LIVE a REELLEMENT eu lieu (`mutated`) -- sans quoi « zero deplacement » serait un
         echec de montage lu comme une mesure ;
      2. le montage est bien DANS LA FENETRE (l'ennemi le plus proche est a 3..5 de la tuile de
         spawn : hors portee d'arme, atteignable apres un pas) ;
      3. le NATIF a bouge ;
      4. le PORT s'arrete sur LA MEME tuile ;
      5. et frappe LA MEME victime.

    ROUGE avant #348 (mesure, meme montage) : le port restait sur sa tuile de spawn et ne frappait
    RIEN, la ou le natif avancait de 15 a 35 et infligeait 9667."""
    r = ai_approach_case("approach")
    assert r["live_mutated"] is True, "le cast LIVE n'a pas mordu -- montage invalide"
    assert 3 <= r["d_near"] <= 5, (
        "ennemi le plus proche a d=%s : hors de la fenetre du regime, le test ne discrimine rien"
        % r["d_near"])
    assert r["live_moved"] is True, (
        "le NATIF n'a pas bouge (%s -> %s) : le montage ne met pas l'approche en jeu"
        % (r["geometry"]["spawn_tile"], r["live_tile"]))
    assert r["off_tile"] == r["live_tile"], (
        "le PORT s'arrete en %s la ou le natif s'arrete en %s -- `GenerateActionTiles(null)` ou "
        "l'apply du `MoveUnitMessage` manquent" % (r["off_tile"], r["live_tile"]))
    assert r["off_victim"] == r["live_victim"] and r["live_victim"] is not None, (
        "victime PORT=%s vs LIVE=%s : l'attaque ne part pas de la tuile finale"
        % (r["off_victim"], r["live_victim"]))


def test_the_actor_stays_put_when_already_in_range(ai_approach_case):
    """REGIME `stay` -- BRAS SYMETRIQUE. L'ennemi est DEJA a portee depuis la tuile de naissance :
    le natif frappe SANS BOUGER (`MovementActionGenerator` est en QUEUE de liste, et le generateur
    d'ability tranche le premier des qu'il produit une action).

    C'est la garde qui interdit la lecture paresseuse « le port bouge, donc c'est bon » : un port
    qui suivrait systematiquement la suggestion de mouvement passerait le test precedent et
    echouerait ici."""
    r = ai_approach_case("stay")
    assert r["live_mutated"] is True, "le cast LIVE n'a pas mordu -- montage invalide"
    assert r["d_near"] <= 2, (
        "ennemi le plus proche a d=%s : le regime `stay` exige une cible DEJA a portee" % r["d_near"])
    assert r["live_moved"] is False, (
        "le NATIF a bouge (%s -> %s) alors que la cible etait a portee -- montage non discriminant"
        % (r["geometry"]["spawn_tile"], r["live_tile"]))
    assert r["off_moved"] is False, (
        "le PORT a DEPLACE l'acteur (%s) alors que le natif reste sur %s" % (r["off_tile"],
                                                                            r["live_tile"]))
    assert r["off_victim"] == r["live_victim"] and r["live_victim"] is not None, (
        "victime PORT=%s vs LIVE=%s" % (r["off_victim"], r["live_victim"]))


def test_pure_move_when_no_attack_is_reachable(ai_approach_case):
    """REGIME `move_only` -- aucune attaque n'est possible depuis AUCUNE tuile d'action : le
    `MovementActionGenerator` ajoute par `allowMoveAction` prend la main et l'acteur ne fait QUE
    s'approcher.

    RESIDU NOMME, et c'est pourquoi la TUILE exacte n'est pas verrouillee ici : le port materialise
    le `unitId` du gameconfig (`astraSmnGuardsman`, traits [Summon, BattleFatigue]) la ou le jeu
    materialise `astraNpc1Guardsman` (traits [BattleFatigue] seuls) -- et le composite de MOUVEMENT
    lit les traits. On verrouille donc ce qui EST attribuable a #348 : les deux BOUGENT, aucun ne
    frappe, et la tuile elue par le NATIF appartient a l'ensemble de candidats du port (preuve que
    `GenerateActionTiles(null)` rend le bon ensemble ; le residu restant est le SCORING)."""
    r = ai_approach_case("move_only")
    assert r["live_mutated"] is True, "le cast LIVE n'a pas mordu -- montage invalide"
    assert r["d_near"] >= 6, (
        "ennemi le plus proche a d=%s : le regime `move_only` exige une cible INATTEIGNABLE"
        % r["d_near"])
    assert r["live_moved"] is True and r["off_moved"] is True, (
        "deplacement pur attendu des DEUX cotes : live=%s port=%s"
        % (r["live_moved"], r["off_moved"]))
    assert not r["live_dmg"] and not r["off_dmg"], (
        "aucun degat n'est possible a cette distance : live=%s port=%s"
        % (r["live_dmg"], r["off_dmg"]))
    assert r["off_tile"] == r["live_tile"] or r.get("live_tile_in_off_reach"), (
        "la tuile elue par le natif (%s) n'est meme pas dans l'ensemble de candidats du port (%s) "
        "-- ce n'est plus un ecart de scoring, c'est `GenerateActionTiles` qui est faux"
        % (r["live_tile"], r.get("off_reach_from_spawn")))
