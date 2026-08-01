"""case-366-r1 -- GARDES de `1216 PsychicStalk_VisualEffect` (`thousAhriman`).

i2 (la 3e phrase du kit) : << The hex of each enemy that is hit by Ahriman's normal ranged attack
catches Fire. >> -- `1216` est le MARQUEUR de cet etat, pas son moteur (la pose du feu est
`PsychicStalk_ApplyFireTileAbility`, non portee).

ARTEFACTS NATIFS (build rnca9r7q6c). La classe `IdunBattle.Entities.Effects.Loki.
PsychicStalk_VisualEffectEffect` surcharge EXACTEMENT quatre methodes, et **aucune n'est un slot de
sortie gameplay** :

  - `PsychicStalk_VisualEffectEffect$$CreateActiveCondition`
        `op_LogicalNot( DSLTriggers.IsDead(Owner@DSLSelectors+0x30) )`
        `IdunBattleLogic.Entities.DSLTriggers$$IsDead` = `op_LogicalNot(DSLTriggers.IsAlive(u))`, et
        `IdunBattle.Entities.Conditions.IsAliveAbilityTrigger$$ShouldTrigger` appelle
        `IdunBattle.Entities.UnitExtensions$$IsAlive` -> `HealthComponent$$IsAlive` = `hp >= 1`.
        Le double NOT se simplifie en `IsAlive(Owner)`.
  - `PsychicStalk_VisualEffectEffect$$CreateTargetSelector`
        `Units( EntitiesWithAnyEffect( Tiles( Enemies(of = Owner@0x30, entities = AllUnits@0x20,
                                                      onlyAlive = 1) ),
                                       Fire = 5, effectTarget = 6 ), unique = 1, selectionType = 3 )`
  - `PsychicStalk_VisualEffectEffect$$GetRefreshTriggers` -- `int[3]`, NON portable (le port n'a ni
        `RefreshEffectTrigger` ni `ShouldRefreshForTrigger`, cf. case-366-r1b).
  - `.ctor`

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :

  * **La CONTRIBUTION NULLE est une MESURE, pas une supposition.** Un effet INERTE n'emet rien, et
    un effet ABSENT non plus : c'est pourquoi le meme coup est rejoue AVEC et SANS `1216` sur la
    MEME capture et le MEME flux MT, dans le regime le PLUS favorable a une contribution (cible sur
    un hex en feu, profil Psychic -> tous les gates du kit OUVERTS). Et un TEMOIN DE SENSIBILITE
    (`sans 1215`) doit, lui, DEPLACER le degat -- sinon l'egalite ne dirait rien d'un montage
    aveugle.
  * **Le SELECTEUR est confronte a un ORACLE INDEPENDANT** derive du live (`tileMeta` +
    `decisionView`), avec un ennemi HORS feu present sur le plateau : sans lui, l'ensemble
    << ennemis >> et l'ensemble << ennemis sur le feu >> coincideraient et un port qui aurait
    OUBLIE le gate `Fire` passerait quand meme. Le montage ASSERTE cette discriminance.
  * **Chaque conjoint du selecteur est eprouve SEUL** (contrefactuels par etage, sur l'etat live
    reel) : retirer le feu, retirer le canal de tuile, echanger l'equipe du porteur, declarer les
    cibles mortes -- chacun doit VIDER l'ensemble.
  * **Le predicat porte DISCRIMINE.** Sur un porteur vivant, `is_active` et le defaut
    `BaseEffect.is_active` rendent TOUS DEUX `True` : l'accord ne prouverait rien. C'est le
    contrefactuel `hp = 0` qui separe -- le port ETEINT (`False`), le defaut reste `True`. Et
    `refresh_stat_modifier_effects` doit ECRIRE le flag, puisque la condition est PORTEE
    (`_active_condition_is_ported`, cf. le bloc de commentaire de `refresh_effects.py`).
  * **La branche FAUSSE est LIVE-INATTEIGNABLE, et c'est MESURE** : quand Ahriman meurt, le natif
    RETIRE les trois effets du kit (liste d'effets VIDE) -- `1216` n'existe donc jamais dans un
    etat ou `IsAlive(Owner)` vaut faux. Le port lit la meme chose sur la meme capture.

Montage complet : `scripts/python/probe_366_r1_psychic_stalk_visual.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_r1_psychic_stalk_visual as PSV

# Deux couples (board, seed) -- discipline de generalisation (runner.md S3) : un resultat obtenu sur
# UN seul board peut etre un artefact de sa geometrie (distances, spawns, terrain).
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))


@pytest.fixture(scope="module")
def psv_case(live_session, rpc):
    """Fabrique : `psv_case(board, seed, kill_carrier)` -> le dict de mesure du probe.

    [!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un
    regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(board: str = "MC1_67", seed: str = "31337", kill_carrier: bool = False) -> dict:
        k = (board, seed, kill_carrier)
        if k not in cache:
            r = PSV.run(rpc, seed=seed, board_id=board, kill_carrier=kill_carrier)
            if r.get("error"):
                pytest.fail("montage PsychicStalk/1216 NON INSTALLE (%s/%s/kill=%s): %s"
                            % (board, seed, kill_carrier, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


@pytest.mark.parametrize("board,seed", COUPLES)
def test_visual_effect_is_deployed_and_active(psv_case, board, seed):
    """E1 -- `1216` est POSE sur Ahriman et son `EffectComponent.IsActive @+0x5c` vaut VRAI.

    C'est la VALEUR DE RETOUR materialisee de `CreateActiveCondition` sur un porteur vivant. Elle se
    lit sur le canal `includeInactive` : le canal par defaut DROPPE les inactifs, donc un zero lu
    la-bas ne serait PAS une mesure."""
    r = psv_case(board, seed)
    assert r["e1_visual_present"] is True, (
        "natif : `1216` ABSENT des effets d'Ahriman au deploiement -- le passif n'est pas monte et "
        "aucune mesure ne porte sur quoi que ce soit (effets vus : %s)"
        % (r["e1_effects_on_carrier"],))
    assert r["e1_visual_name"] == "PsychicStalk_VisualEffect", (
        "nom capte inattendu : %s" % (r["e1_visual_name"],))
    assert r["e1_visual_active"] is True, (
        "natif : `1216` pose mais INACTIF sur un porteur VIVANT -- `CreateActiveCondition` = "
        "`NOT IsDead(Owner)` devrait rendre VRAI (effets vus : %s)" % (r["e1_effects_on_carrier"],))
    # les trois effets du kit vivent sur le MEME porteur (`CreateBehaviour` = 3 x AddEffect(Owner))
    types = {t for t, _n, _a in r["e1_effects_on_carrier"]}
    assert {1215, 1216, 1435} <= types, (
        "le kit PsychicStalk n'est pas COMPLET sur Ahriman : %s" % (sorted(types),))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_target_selector_matches_the_live_oracle(psv_case, board, seed):
    """E2 -- le mirror de `CreateTargetSelector` designe EXACTEMENT les ennemis vivants du porteur
    dont la main tile porte `Fire`, d'apres un ORACLE INDEPENDANT (`tileMeta` + `decisionView`).

    La garde de MONTAGE (un ennemi HORS feu doit exister) vit dans le probe et FAIT ECHOUER le cas :
    sans elle, un port qui aurait oublie le gate `Fire` passerait."""
    r = psv_case(board, seed)
    sel = r["e2_selector"]
    assert sel.get("present") is True, (
        "le port ne materialise PAS 1216 sur la capture -- l'inscription EFFECT_CLASSES "
        "['PsychicStalk_VisualEffect'] manque (effets vus : %s)" % (sel.get("effects_on_carrier"),))
    assert sel.get("cls") == "PsychicStalkVisualEffect", (
        "1216 est route sur %s (attendu PsychicStalkVisualEffect)" % sel.get("cls"))
    assert r["e2_enemies_off_fire"], "montage non discriminant : aucun ennemi HORS feu"
    assert sel["covered"] == r["e2_oracle_enemies_on_fire"], (
        "selecteur porte = %s, oracle LIVE (ennemis vivants sur un hex en feu) = %s ; ennemis HORS "
        "feu = %s, feu = %s" % (sel["covered"], r["e2_oracle_enemies_on_fire"],
                                r["e2_enemies_off_fire"], r["fire_tiles"]))
    for uid in r["e2_enemies_off_fire"]:
        assert uid not in sel["covered"], (
            "u%d est ENNEMI mais PAS sur un hex en feu, et le selecteur le retient quand meme -- "
            "le noeud `EntitiesWithAnyEffect(Tiles(...), Fire = 5)` ne ferme pas" % uid)


@pytest.mark.parametrize("board,seed", COUPLES)
def test_each_selector_conjunct_closes_the_set(psv_case, board, seed):
    """E2bis -- DECOMPOSITION PAR ETAGE du selecteur : chaque conjoint, neutralise SEUL sur l'etat
    live reel, doit VIDER l'ensemble. Un ensemble qui reste non vide nomme le noeud manquant."""
    sel = psv_case(board, seed)["e2_selector"]
    assert sel["cov_no_fire"] == [], (
        "feu retire de TOUTES les tuiles et le selecteur designe encore %s -- le noeud "
        "`EntitiesWithAnyEffect(..., Fire = 5, effectTarget = 6)` est absent" % (sel["cov_no_fire"],))
    assert sel["cov_no_tile_channel"] == [], (
        "canal de tuile ABSENT (None) et le selecteur designe %s -- la degradation doit etre "
        "RESTRICTIVE (cle absente = gate ferme), jamais permissive" % (sel["cov_no_tile_channel"],))
    assert sel["cov_owner_team_swapped"] == [], (
        "le porteur a recu l'equipe des ennemis (ils deviennent ses ALLIES) et le selecteur designe "
        "encore %s -- le noeud `Enemies(of = Owner@0x30)` est absent"
        % (sel["cov_owner_team_swapped"],))
    assert sel["cov_team_unknown"] == [], (
        "equipe du porteur INCONNUE et le selecteur designe %s" % (sel["cov_team_unknown"],))
    assert sel["cov_all_dead"] == [], (
        "toutes les cibles declarees MORTES et le selecteur designe encore %s -- le "
        "`onlyAlive = 1` d'`Enemies` (reexpedie en selectionType 3) est absent"
        % (sel["cov_all_dead"],))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_visual_effect_contributes_nothing_to_damage(psv_case, board, seed):
    """E3 -- LA garde centrale. `1216` n'ecrit dans AUCUN slot de `DamageModifiers`, et c'est
    MESURE dans le regime le PLUS favorable a une contribution : cible SUR un hex en feu, profil
    Psychic -> les gates du kit sont OUVERTS (le voisin `1215` tire, lui).

    Le TEMOIN DE SENSIBILITE est indispensable : `sans 1215` doit DEPLACER le degat. Sans lui,
    << retirer 1216 ne change rien >> serait aussi ce que rendrait un montage aveugle."""
    r = psv_case(board, seed)
    assert r["e3_dirty"] is False, "coup SALE (crit/block/evade) -- non comparable a un rejeu"
    assert r["target_on_fire"] is True, "la cible n'est pas sur un hex en feu : gate ferme"
    assert r["e3_port_hits"] == r["e3_live_hits"], (
        "port %s != natif %s sur le coup de reference" % (r["e3_port_hits"], r["e3_live_hits"]))
    assert r["e3_port_hits_without_visual"] == r["e3_port_hits"], (
        "retirer `1216` du monde offline CHANGE le degat (%s -> %s) : la classe a acquis un canal "
        "de degat que le natif n'a pas -- `PsychicStalk_VisualEffectEffect` ne surcharge AUCUN slot "
        "de sortie" % (r["e3_port_hits"], r["e3_port_hits_without_visual"]))
    assert r["e3_stage_without_visual"] == r["e3_stage_with"], (
        "les ETAGES bougent quand on retire `1216` : avec=%s sans=%s -- un scalaire final egal ne "
        "suffit pas, c'est le slot qui doit etre inchange"
        % (r["e3_stage_with"], r["e3_stage_without_visual"]))
    # TEMOIN DE SENSIBILITE -- le montage VOIT-IL une contribution quand il y en a une ?
    assert r["e3_port_hits_without_extra"] != r["e3_port_hits"], (
        "retirer `1215` (qui, LUI, alimente le %%-list DEFENSEUR) ne change PAS le degat (%s) : le "
        "montage est AVEUGLE, et l'egalite obtenue pour 1216 ne prouve donc rien"
        % (r["e3_port_hits"],))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_active_condition_is_ported_and_discriminates(psv_case, board, seed):
    """E5 -- le predicat porte est une LECTURE, pas le defaut.

    Sur un porteur vivant, `is_active` et `BaseEffect.is_active` rendent TOUS DEUX True : c'est le
    contrefactuel `hp = 0` qui SEPARE. Et le flag doit etre RE-ECRIT par le refresh, puisque la
    condition est portee (`_active_condition_is_ported` -> branche << re-evaluer >>)."""
    av = psv_case(board, seed)["e5_active_view"]
    nom, dead = av["nominal"], av["hp_zero"]
    assert nom["condition_ported"] is True, (
        "`_active_condition_is_ported` rend FAUX : la classe ne surcharge plus `is_active`, donc "
        "le refresh CONSERVE le flag au lieu de re-evaluer la condition")
    assert nom["is_active"] is True and nom["flag_after_refresh"] is True, (
        "porteur VIVANT (hp=%s) et le port ETEINT l'effet : %s" % (nom["hp"], nom))
    assert dead["is_active"] is False, (
        "porteur a hp=0 et le port garde `1216` ACTIF -- `NOT IsDead(Owner)` n'est pas lu")
    assert dead["base_default"] is True, (
        "le defaut `BaseEffect.is_active` ne rend plus True : le contrefactuel ne DISCRIMINE plus "
        "et cette garde ne prouve plus que la condition est lue")
    assert dead["flag_after_refresh"] is False, (
        "`refresh_stat_modifier_effects` n'a pas ETEINT le flag alors que la condition portee est "
        "fausse (%s)" % (dead,))


def test_dead_carrier_drops_the_whole_kit(psv_case):
    """E4 -- LA BRANCHE FAUSSE, cote NATIF. Quand Ahriman meurt, le natif ne laisse pas `1216`
    INACTIF : il RETIRE les trois effets du kit. La branche `IsAlive(Owner) == False` est donc
    LIVE-INATTEIGNABLE en regime etabli -- resultat MESURE, pas abandon. Le port lit la meme chose
    sur la meme capture (aucune instance de son cote non plus)."""
    r = psv_case("MC1_67", "31337", kill_carrier=True)
    assert r["e1_visual_present"] is True, "1216 absent AVANT la mort : le bras ne mesure rien"
    assert r["e4_carrier_isdead_observe"] is True, (
        "le porteur n'est pas mort (observeBattle.isDead=%s hp=%s) -- le bras ne mesure pas la "
        "branche voulue" % (r["e4_carrier_isdead_observe"], r["e4_carrier_hp"]))
    assert r["e4_effects_on_carrier"] == [], (
        "natif : le porteur est MORT mais garde des effets %s -- si `1216` y survivait INACTIF, la "
        "branche fausse serait observable et cette garde devrait mesurer son flag"
        % (r["e4_effects_on_carrier"],))
    assert r["e4_visual_present"] is False
    # PARITE : le port ne materialise pas davantage d'instance que le natif.
    assert r["e4_port_active_view"]["nominal"] is None, (
        "le port materialise une instance de `1216` la ou le natif n'en a plus : %s"
        % (r["e4_port_active_view"],))
