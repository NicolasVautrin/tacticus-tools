"""CONFRONT LIVE de `1064 Loki_SwoopingHawk` (`eldarAutarch` Aethana, Aeldari, HERO) -- #502.

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * la TOPOLOGIE de la vague. Le decompile de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase$$GetTargetTilesSelector`
    prolonge une LIGNE `TilesBehindInLine(CasterTile, <tuile de contact de la cible>)` et en prend
    les TROIS premieres tuiles ; `ExecuteBehaviour` deroule un montant PAR RANG (`dmg[0..2]`). Le
    patron voisin -- un splash sur les ennemis ADJACENTS a la cible -- donnerait le meme ENSEMBLE
    de cibles sur une geometrie compacte, mais jamais TROIS montants DIFFERENTS. Le montage aligne
    trois ennemis en colonne : c'est ce qui separe les deux modeles, et rien d'autre ne les separe.
  * le DEGAT, RANG PAR RANG, `state.rng` CALE sur le MT live. C'est ce qui DECOMPOSE `pierce`
    (profil `Piercing` -> `PiercingRatio` -> armure) et `dmg_bonus` (mods ATTAQUANT, multiplicatifs
    et COMMUNS aux trois rangs) au lieu de les absorber dans un total : un total juste peut cacher
    deux etages faux qui se compensent. Le ratio `montant / dmg[rang]` doit etre le MEME a tous les
    rangs non bloques -- c'est ce qui prouve que le port indexe `dmg[i]` et n'a pas fige un montant.
  * l'ABSENCE DE CRIT, qui est un OBSERVABLE et non une simplification : `DSLBehaviors$$AbilityDamage`
    construit un `AbilityDamageBehaviour` -> `IdunBattle.Operations.AbilityDamageOperation`, et
    cette famille n'a AUCUN slot `RollCritical`. Un port qui router la famille ATTACK
    (`AttackDamageOperation`) ferait crit, et consommerait deux tirages par coup au lieu d'un.
  * l'ATTERRISSAGE, sur ses DEUX branches. `GetMovementBehavior` est un `ConditionalSelector` :
    branche VRAIE = la tuile derriere la derniere cible, branche FAUSSE = la tuile libre la plus
    proche d'elle (celle qui porte un `Randomize`, donc du PRNG). Les deux sont gardees.
  * l'ANCRE du deplacement -- la garde la plus fine du fichier. `ExecuteBehaviour` EVALUE ses
    selecteurs A LA CONSTRUCTION pour retenir la DERNIERE tuile PORTANT un ennemi, pas la derniere
    tuile de la ligne. Avec une seule cible, les deux lectures divergent (tuile 2 vs tuile 4) et un
    port qui prendrait « la fin de la ligne » passe tous les autres scenarios et tombe ici.
  * l'ORDRE DES ARGUMENTS de `TileBehindTargetFromSourceDirection`. La factory prend
    `(target, source)`, le selecteur construit lit `(Select(+0x18) = source, Select(+0x20) = target)`
    -- les deux sont INVERSES. S'en remettre au nom ferait atterrir le caster ENTRE lui et sa cible ;
    c'est la position finale qui le refute.
  * le GATE DE CIBLAGE. `TARGETING_OPTIONS` absent => `get_invalid_target_reason` rend 0
    immediatement : le moteur accepterait des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Degradation PERMISSIVE,
    ni erreur ni crash, invisible en self-play -- exactement le trou qu'un entrainement exploiterait.
  * le CONTRAT DE DISJONCTION. Une ability portee porte son masque sur SA classe, jamais dans
    `TARGETING_OPTIONS_UNPORTED` : deux copies divergeraient en silence.

TEMOIN DE NON-DEGENERESCENCE : les gardes de degat exigent des montants NON NULS et DEUX A DEUX
DIFFERENTS. Un accord obtenu la ou personne ne prend rien -- ou la ou les trois rangs prennent la
meme chose -- ne prouve rien, et le fichier le dit au lieu de verdir.

RESIDU NOMME, MESURE et NON GARDE ICI (`#502-r1`) : `StartAttack` / `FinishAttack`. Le natif encadre
chaque maillon par ces deux behaviours (`If(!AreEqual(cur, prev), StartAttack)` /
`If(!AreEqual(cur, next), FinishAttack)`), dont le seul effet observable est de FUSIONNER en UNE
attaque les tuiles consecutives occupees par la MEME unite -- une grande unite couchee sur deux
rangs de la ligne. Le port n'a pas de substrat DSL pour la pile de contexte d'attaque
(`MatchState+0x60`) et emet une attaque PAR TUILE : total de degats identique, nombre d'attaques
encadrantes different. Aucun test n'est ecrit dessus : un test qui ASSERTE la divergence figerait
le residu. Il faut une unite multi-hex alignee pour le mesurer.

Le montage (build + DRIVE des positions par `--place`/`--a-place`) et TOUTES les lectures vivent
dans `scripts/python/probe_502_swooping_hawk.py` : le probe MESURE, ce test GARDE, une seule
implementation -- aucune divergence possible entre les deux.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee hors du montage, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_502_swooping_hawk as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE, pas une facilite : ce fichier importe le PROBE, qui
    # importe `ABILITY_CLASSES` -- sa fermeture d'import atteint la quasi-totalite de
    # `scripts/python` (~139 modules pour un test d'ability). Declarer etroit produirait un FAUX
    # VERT : le test ne serait pas rejoue quand ce qu'il mesure change.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "scripts/python/tests/conftest.py", "scripts/python/tests/engine/conftest.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle de toutes les gardes (topologie, degat rang par rang, crit,
    # atterrissage, ancre, gate) : un changement de build peut les faire changer d'avis sans
    # qu'une ligne du port bouge.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de 1064. Le verdict depend du code du port (arbre "
              "DSL de la vague + selecteurs de ligne / tuile-derriere / conditionnel + la feuille "
              "d'attaque d'ability + la geometrie hex de `battle_query` + le registre + le masque "
              "de ciblage), du MONTAGE (le probe, qui porte le drive des positions et TOUTES les "
              "lectures), des entrees versionnees du runner, et du BUILD charge -- l'oracle etant "
              "le jeu lui-meme, pas une constante ecrite ici. Le perimetre est pris a tout "
              "`scripts/python` parce que la fermeture d'import du probe y atteint des chemins "
              "qu'aucune liste explicite n'aurait devines.",
}

SWOOPING_HAWK = P.SWOOPING_HAWK                  # 1064 ActiveAbilityType.Loki_SwoopingHawk


@pytest.fixture(scope="module")
def vague(live_session):
    """Runner NOMINAL : trois ennemis alignes derriere le caster. Le cast est joue une fois des DEUX
    cotes, les gardes relisent la MEME mesure (le cast n'est pas rejouable -- il consomme l'actif)."""
    m, dispose = P.measure(live_session, state_name="test_502_vague")
    try:
        yield m
    finally:
        dispose()


@pytest.fixture(scope="module")
def repli(live_session):
    """Runner REPLI : la tuile d'atterrissage est OCCUPEE. Il exerce la branche FAUSSE du
    `ConditionalSelector` -- la seule qui evalue le `Randomize`, donc la seule ou le choix de tuile
    passe par le PRNG. Sans lui, la branche vraie couvrirait a elle seule tout l'etage MOUVEMENT."""
    m, dispose = P.measure(live_session, state_name="test_502_repli", avec_bouchon=True)
    try:
        yield m
    finally:
        dispose()


@pytest.fixture(scope="module")
def ancre(live_session):
    """Runner ANCRE : UNE seule cible, les deux tuiles suivantes de la ligne sont VIDES. C'est le
    seul montage ou « derniere tuile OCCUPEE » et « derniere tuile de la ligne » donnent des
    reponses DIFFERENTES."""
    m, dispose = P.measure(live_session, state_name="test_502_ancre", n_cibles=1)
    try:
        yield m
    finally:
        dispose()


def test_swooping_hawk_execution_est_portee(vague):
    """La face EXECUTION est portee : sans elle, la decision CHOISIT le cast et l'execution
    l'IGNORE -- 0 degat, 0 effet, AUCUNE erreur (le no-op silencieux que #502 ferme)."""
    assert vague["routed"] == "handler" and vague["ported"] is True, \
        "1064 non portee (routed=%s ported=%s)" % (vague["routed"], vague["ported"])
    assert not vague["cast_error"], "cast natif bloque: %s" % vague["cast_error"]
    assert vague["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"


def test_swooping_hawk_la_vague_frappe_les_trois_tuiles_de_la_ligne(vague):
    """LA garde de topologie : l'ensemble des cibles frappees, port == natif == les trois tuiles
    alignees. Le 3e rang est a DEUX hex de la cible primaire."""
    assert len(vague["live_wave"]) == 3, \
        "le NATIF ne frappe pas 3 tuiles : %s" % (vague["live_wave"],)
    assert sorted(vague["off_wave"]) == sorted(vague["live_wave"]), \
        "topologie port != natif : %s vs %s" % (vague["off_wave"], vague["live_wave"])


def test_swooping_hawk_degat_rang_par_rang_bit_exact(vague):
    """Le DEGAT, rang par rang, sur MT COMMUN -- l'egalite est BIT-EXACTE, pas approchee.

    Le temoin de non-degenerescence est ASSERTE et non suppose : sans montants non nuls ET deux a
    deux differents, l'accord ne separerait pas le modele LIGNE du modele SPLASH."""
    montants = [m for m, bloque in vague["rangs"] if not bloque]
    assert len(montants) >= 2 and all(m > 0 for m in montants), \
        "REGIME DEGENERE : montants non-bloques = %s -- l'accord ne prouverait rien" % (montants,)
    assert len(set(montants)) == len(montants), \
        "REGIME DEGENERE : les rangs prennent le MEME montant (%s) -- un splash serait " \
        "indiscernable d'une vague" % (montants,)
    assert sorted(vague["off_delta"].items()) == sorted(vague["live_delta"].items()), \
        "degat port != natif : %s vs %s" % (sorted(vague["off_delta"].items()),
                                            sorted(vague["live_delta"].items()))


def test_swooping_hawk_le_montant_est_indexe_par_rang(vague):
    """`dmg_bonus` SEPARE de `pierce` : les mods ATTAQUANT sont multiplicatifs et COMMUNS aux trois
    rangs, donc le ratio `montant / dmg[rang]` doit etre le MEME partout. Un port qui figerait un
    seul montant (au lieu d'indexer `dmg[i]`) ferait DERIVER ce ratio rang a rang, alors meme que
    le total resterait plausible."""
    ratios = [r for r in P._ratios(vague["rangs"], vague["damages_config"]) if r is not None]
    assert len(ratios) >= 2, "moins de 2 rangs exploitables (%s) : la garde ne mord pas" % (ratios,)
    assert max(ratios) - min(ratios) < 0.01, \
        "le ratio montant/dmg DERIVE selon le rang (%s) : le montant n'est pas indexe par rang" \
        % (ratios,)


def test_swooping_hawk_famille_ability_donc_aucun_crit(vague):
    """`DSLBehaviors$$AbilityDamage` -> `AbilityDamageOperation` : cette famille n'a AUCUN slot
    `RollCritical`. Le natif ne crit donc JAMAIS sur cette vague -- c'est un OBSERVABLE, et c'est
    ce qui distingue la route portee de la famille ATTACK (qui crit et consomme 2 tirages/coup)."""
    assert vague["live_crit"], "aucun coup mesure : la garde ne mord pas"
    assert all(c == 0 for c in vague["live_crit"]), \
        "le natif a CRIT sur une attaque d'ability : %s" % (vague["live_crit"],)


def test_swooping_hawk_profil_de_degat_est_celui_de_la_config(vague):
    """`pierce` SEPARE : le `DamageProfileType` de CHAQUE coup natif == l'ordinal du profil lu au
    gameconfig (`GetDamageProfile` = « Piercing »), jamais une constante transcrite ici."""
    attendu = P.profil_ordinal()
    assert attendu >= 0, "le profil de 1064 ne resout pas dans PROFILE_NAME_BY_INDEX"
    assert vague["live_profile"] == [attendu], \
        "profil natif %s != %s (config)" % (vague["live_profile"], attendu)


def test_swooping_hawk_atterrit_derriere_la_derniere_cible(vague):
    """L'ATTERRISSAGE, branche VRAIE : le caster finit sur la tuile un pas AU-DELA du dernier rang
    touche. C'est aussi ce qui refute l'ordre d'arguments inverse -- la tuile « devant » serait
    entre le caster et sa cible, dans l'autre sens."""
    assert vague["live_caster_pos"][1] == P.LANDING_TILE, \
        "le NATIF n'atterrit pas derriere le 3e rang : %s" % (vague["live_caster_pos"],)
    assert vague["off_caster_pos"][1] == vague["live_caster_pos"][1], \
        "position finale port != natif : %s vs %s" % (vague["off_caster_pos"][1],
                                                      vague["live_caster_pos"][1])


def test_swooping_hawk_repli_quand_la_tuile_est_occupee(repli):
    """L'ATTERRISSAGE, branche FAUSSE du `ConditionalSelector` : la tuile derriere est OCCUPEE, le
    natif prend « la tuile libre la plus proche ». Le port doit trouver LA MEME -- ce qui exige que
    le pool, son `Randomize` et le tri par distance soient tous alignes."""
    assert repli["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"
    assert repli["live_caster_pos"][1] != P.LANDING_TILE, \
        "la tuile d'atterrissage n'etait pas occupee : le scenario n'exerce PAS le repli"
    assert repli["live_caster_pos"][1] != repli["live_caster_pos"][0], \
        "le natif n'a pas bouge : la branche de repli n'a rien rendu"
    assert repli["off_caster_pos"][1] == repli["live_caster_pos"][1], \
        "repli port != natif : %s vs %s" % (repli["off_caster_pos"][1],
                                            repli["live_caster_pos"][1])


def test_swooping_hawk_ancre_sur_la_derniere_tuile_OCCUPEE(ancre):
    """L'ANCRE : avec UNE seule cible, l'atterrissage se fait derriere ELLE, pas au bout de la
    ligne. Les deux tuiles sont distinctes -- c'est ce qui rend la garde discriminante."""
    derriere_rang1 = (P.WAVE_TILES[0][0], P.WAVE_TILES[0][1] + 1)
    assert derriere_rang1 != P.LANDING_TILE, \
        "montage non discriminant : les deux lectures donneraient la meme tuile"
    assert len(ancre["live_wave"]) == 1, \
        "le montage ANCRE ne porte pas exactement 1 cible : %s" % (ancre["live_wave"],)
    assert ancre["live_caster_pos"][1] == derriere_rang1, \
        "le NATIF n'ancre pas sur la derniere tuile OCCUPEE : %s" % (ancre["live_caster_pos"],)
    assert ancre["off_caster_pos"][1] == ancre["live_caster_pos"][1], \
        "ancre port != natif : %s vs %s" % (ancre["off_caster_pos"][1],
                                            ancre["live_caster_pos"][1])


def test_swooping_hawk_gate_de_ciblage_mord(vague):
    """Le masque `TargetIsEnemy` (0x4000) MORD : un allie et le caster lui-meme sont REFUSES, et
    l'oracle du refus est le natif (`abilityTargets` ne les enumere pas)."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    assert vague["gate"]["ennemi"] == 0, "un ENNEMI est refuse par le port : %s" % vague["gate"]
    assert vague["gate"]["allie"] == int(TR.TargetIsEnemy), \
        "un ALLIE n'est pas refuse par TargetIsEnemy : %s" % vague["gate"]
    assert vague["gate"]["soi"] == int(TR.TargetIsEnemy), \
        "le CASTER n'est pas refuse par TargetIsEnemy : %s" % vague["gate"]
    assert vague["gate_natif"]["allie_dans_targets"] is False, \
        "le NATIF proposerait un allie -- le masque lu serait faux"
    assert vague["gate_natif"]["soi_dans_targets"] is False, \
        "le NATIF proposerait le caster -- le masque lu serait faux"


def test_swooping_hawk_masque_a_une_seule_source():
    """CONTRAT DE DISJONCTION : 1064 est au registre, donc son masque vit sur SA classe et NULLE
    PART ailleurs. Deux sources divergeraient en silence."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
    assert SWOOPING_HAWK in ABILITY_CLASSES, "1064 n'est pas au registre"
    assert SWOOPING_HAWK not in TARGETING_OPTIONS_UNPORTED, \
        "1064 a DEUX sources de masque (registre + TARGETING_OPTIONS_UNPORTED)"
    assert getattr(ABILITY_CLASSES[SWOOPING_HAWK], "TARGETING_OPTIONS", None) is not None, \
        "1064 est au registre SANS masque -- gate permissif silencieux"
    assert SWOOPING_HAWK in ABILITY_ATTACK_TYPE, \
        "1064 est au registre SANS son litteral AbilityAttackType"
