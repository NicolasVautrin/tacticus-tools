"""CONFRONT LIVE de `1091 SlashingDive` (`thousNpc2Screamer` « Screamer », Thousand Sons) -- #507.

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * le PARTAGE DE LA BASE, qui est la question meme de la tranche. `SlashingDiveAbility` n'a AUCUN
    symbole propre dans les tables (IL2CPP a FUSIONNE son ctor avec celui de `SwoopingHawkAbility` --
    les deux corps sont `return DiveAttackAbilityBase$$.ctor(this);` -- et ces tables sont indexees
    par ADRESSE) : c'est ce faux negatif qui l'avait fait classer NON-LU. Ce fichier garde la
    consequence OBSERVABLE du partage : le comportement de 1091 est celui de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase`, a la CONFIG pres.
  * la CONFIG RELUE PAR ABILITY, et c'est la garde qui separe 1091 de sa soeur. Le profil de degat
    de 1091 est `Power`, celui de 1064 `Piercing` : un port qui aurait recopie la constante de la
    voisine tombe ici. Contre-epreuve MESUREE (mutation du seul `dive_attack_profile` -> `Piercing`
    sur le montage nominal) : le port passe de `1477/1164/873` a `2910/2328/1746`, le natif ne
    bouge pas -- la garde MORD.
  * la TOPOLOGIE de la vague : trois tuiles ALIGNEES, un montant PAR RANG (`dmg[0..2]`). Le patron
    voisin -- un splash sur les ennemis ADJACENTS a la cible -- donnerait le meme ENSEMBLE de cibles
    sur une geometrie compacte, mais jamais TROIS montants DIFFERENTS. Contre-epreuve MESUREE
    (mutation `dmg = [dmg0]*3`) : le port rend `1477/1477/1477`, divergence -- la garde MORD.
  * le DEGAT, RANG PAR RANG, `state.rng` CALE sur le MT live. C'est ce qui DECOMPOSE `pierce`
    (profil `Power` -> `PiercingRatio` -> armure) et `dmg_bonus` (mods ATTAQUANT, multiplicatifs et
    COMMUNS aux trois rangs) au lieu de les absorber dans un total : un total juste peut cacher deux
    etages faux qui se compensent.
  * l'ABSENCE DE CRIT, qui est un OBSERVABLE et non une simplification : `DSLBehaviors$$AbilityDamage`
    construit un `AbilityDamageBehaviour` -> `IdunBattle.Operations.AbilityDamageOperation`, et cette
    famille n'a AUCUN slot `RollCritical`.
  * le BLOCK, qui est l'autre face du meme etage : sous un MT ou le 2e rang bloque, le montant natif
    vaut 0 et la cible ne perd AUCUN PV. Le port doit suivre. Sans ce scenario, le montage nominal
    (choisi justement pour qu'aucun rang ne bloque) laisserait cette branche non confrontee.
  * l'ATTERRISSAGE, sur ses DEUX branches. `GetMovementBehavior` est un `ConditionalSelector` :
    branche VRAIE = la tuile derriere la derniere cible, branche FAUSSE = la tuile libre la plus
    proche d'elle (celle qui porte un `Randomize`, donc du PRNG).
  * l'ANCRE du deplacement -- la garde la plus fine du fichier. `ExecuteBehaviour` EVALUE ses
    selecteurs A LA CONSTRUCTION pour retenir la DERNIERE tuile PORTANT un ennemi, pas la derniere
    tuile de la ligne. Avec une seule cible, les deux lectures divergent et un port qui prendrait
    « la fin de la ligne » passe tous les autres scenarios et tombe ici.
  * la LETALITE, et avec elle le corollaire le plus contre-intuitif du decompile : `last` est fige
    AU CAST, donc quand les trois cibles MEURENT le caster atterrit quand meme derriere le CADAVRE
    du 3e rang. Un port qui recalculerait l'ancre apres les degats ne trouverait plus personne.
  * le GATE DE CIBLAGE. `TARGETING_OPTIONS` absent => `get_invalid_target_reason` rend 0
    immediatement : le moteur accepterait des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Degradation PERMISSIVE,
    ni erreur ni crash, invisible en self-play.
  * le CONTRAT DE DISJONCTION. Une ability portee porte son masque sur SA classe, jamais dans
    `TARGETING_OPTIONS_UNPORTED`.

TEMOIN DE NON-DEGENERESCENCE : les gardes de degat exigent des montants NON NULS et DEUX A DEUX
DIFFERENTS. Un accord obtenu la ou personne ne prend rien -- ou la ou les trois rangs prennent la
meme chose -- ne prouve rien, et le fichier le dit au lieu de verdir.

CE QUI N'EST PAS COUVERT, et qui ne l'est pas par une limite du PORT mais du PORTEUR :
  * `attackRangeType` (l'axe `is_melee`). Contre-epreuve MESUREE : forcer `is_melee = False` NE
    change RIEN au degat, parce que le Screamer n'a qu'UNE arme (`weapons` = un seul bloc, sans
    `Range`) -- les deux branches lisent la meme. L'axe est INERTE POUR CE PORTEUR, et les trois
    porteurs de 1091 sont tous des Screamers. La valeur reste RELUE de la config (jamais codee en
    dur), ce qui est ce que la doctrine exige ; elle n'est simplement pas discriminee ici.
  * `StartAttack` / `FinishAttack` (residu herite de #502-r1) : leur seul effet observable est de
    FUSIONNER en UNE attaque les tuiles consecutives occupees par la MEME unite -- il faut une unite
    MULTI-HEX alignee pour le mesurer. Aucun test ne l'asserte : un test qui ASSERTE la divergence
    figerait le residu.
  * `DiveAttackAbilityBase$$GetTargetUnitsSelector` -- l'accesseur de la face PREDICTION/UI. Il
    n'est pas porte (ni pour 1064, ni pour 1091) et n'entre pas dans `ExecuteBehaviour`.

GATE DE CONFRONTABILITE : 1091 n'a AUCUN porteur lineup (`thousNpc2Screamer` npc, `thousSmnScreamer`
et `thousSmnScreamerHSE` summons). Le npc porte une table `units.npc[].stats[]`, donc il arrive en
bataille par le CHEMIN DE STATS EXPLICITE (`--explicit-stats thousNpc2Screamer:45`) avec SES stats,
SES traits et SON arme -- c'est le mirror du catalogue, pas un montage, et il est COMMANDABLE. Ni
greffe d'ability ni injection catalogue n'ont ete necessaires.

Le montage (build + DRIVE des positions par `--place`/`--a-place`) et TOUTES les lectures vivent
dans `scripts/python/probe_507_slashing_dive.py` : le probe MESURE, ce test GARDE, une seule
implementation -- aucune divergence possible entre les deux.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee hors du montage, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_507_slashing_dive as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE, pas une facilite : ce fichier importe le PROBE, qui
    # importe `ABILITY_CLASSES` -- sa fermeture d'import atteint la quasi-totalite de
    # `scripts/python`. Declarer etroit produirait un FAUX VERT : le test ne serait pas rejoue
    # quand ce qu'il mesure change.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "scripts/python/tests/conftest.py", "scripts/python/tests/engine/conftest.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle de toutes les gardes (topologie, degat rang par rang, crit, block,
    # atterrissage, ancre, letalite, gate) : un changement de build peut les faire changer d'avis
    # sans qu'une ligne du port bouge.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de 1091. Le verdict depend du code du port (la base "
              "`DiveAttackAbilityBase` partagee avec 1064 -- arbre DSL de la vague + selecteurs de "
              "ligne / tuile-derriere / conditionnel + la feuille d'attaque d'ability + la "
              "geometrie hex de `battle_query` + le registre + le masque de ciblage), du MONTAGE "
              "(le probe, qui porte le drive des positions, le chemin de stats explicite npc et "
              "TOUTES les lectures), des entrees versionnees du runner, et du BUILD charge -- "
              "l'oracle etant le jeu lui-meme, pas une constante ecrite ici.",
}

SLASHING_DIVE = P.SLASHING_DIVE                  # 1091 ActiveAbilityType.SlashingDive


def _mesure(live_session, **kw):
    """Monte le scenario, LIT tout, puis DISPOSE IMMEDIATEMENT le runner.

    Le `dispose` n'attend pas le teardown du module : la mesure est un dict de scalaires deja lu,
    plus rien n'a besoin du runner. Avec cinq scenarios, garder chaque runner vivant jusqu'a la fin
    du fichier immobiliserait cinq places du budget PARTAGE (cf. `runner.md` §3) pour rien."""
    m, dispose = P.measure(live_session, **kw)
    dispose()
    return m


@pytest.fixture(scope="module")
def vague(live_session):
    """Runner NOMINAL : trois ennemis alignes derriere le caster, sous un MT ou AUCUN rang ne bloque
    -- c'est ce qui donne trois montants non nuls et deux a deux distincts."""
    return _mesure(live_session, state_name="test_507_vague")


@pytest.fixture(scope="module")
def repli(live_session):
    """Runner REPLI : la tuile d'atterrissage est OCCUPEE. Il exerce la branche FAUSSE du
    `ConditionalSelector` -- la seule qui evalue le `Randomize`, donc la seule ou le choix de tuile
    passe par le PRNG."""
    return _mesure(live_session, state_name="test_507_repli", avec_bouchon=True)


@pytest.fixture(scope="module")
def ancre(live_session):
    """Runner ANCRE : UNE seule cible, les deux tuiles suivantes de la ligne sont VIDES. C'est le
    seul montage ou « derniere tuile OCCUPEE » et « derniere tuile de la ligne » donnent des
    reponses DIFFERENTES."""
    return _mesure(live_session, state_name="test_507_ancre", n_cibles=1)


@pytest.fixture(scope="module")
def letal(live_session):
    """Runner LETAL : les trois cibles MEURENT sous la vague (PV forces bas, plus un ennemi lointain
    pour que la bataille ne s'achete pas). Il exerce la letalite ET l'ancre figee AU CAST."""
    return _mesure(live_session, state_name="test_507_letal", letal=True)


@pytest.fixture(scope="module")
def bloque(live_session):
    """Runner BLOCK : meme montage, un MT ou le 2e rang BLOQUE. La branche block du degat n'est
    exercee par AUCUN autre scenario du fichier (le nominal est choisi pour ne pas bloquer)."""
    return _mesure(live_session, state_name="test_507_block", seed=P.SEED_BLOCK)


def test_slashing_dive_execution_est_portee(vague):
    """La face EXECUTION est portee : sans elle, la decision CHOISIT le cast et l'execution
    l'IGNORE -- 0 degat, 0 effet, AUCUNE erreur (le no-op silencieux que #507 ferme)."""
    assert vague["routed"] == "handler" and vague["ported"] is True, \
        "1091 non portee (routed=%s ported=%s)" % (vague["routed"], vague["ported"])
    assert not vague["cast_error"], "cast natif bloque: %s" % vague["cast_error"]
    assert vague["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"


def test_slashing_dive_la_vague_frappe_les_trois_tuiles_de_la_ligne(vague):
    """LA garde de topologie : l'ensemble des cibles frappees, port == natif == les trois tuiles
    alignees. Le 3e rang est a DEUX hex de la cible primaire."""
    assert len(vague["live_wave"]) == 3, \
        "le NATIF ne frappe pas 3 tuiles : %s" % (vague["live_wave"],)
    assert sorted(vague["off_wave"]) == sorted(vague["live_wave"]), \
        "topologie port != natif : %s vs %s" % (vague["off_wave"], vague["live_wave"])


def test_slashing_dive_degat_rang_par_rang_bit_exact(vague):
    """Le DEGAT, rang par rang, sur MT COMMUN -- l'egalite est BIT-EXACTE, pas approchee.

    Le temoin de non-degenerescence est ASSERTE et non suppose : sans TROIS montants non nuls ET
    deux a deux differents, l'accord ne separerait pas le modele LIGNE du modele SPLASH."""
    montants = [m for m, b in vague["rangs"] if not b]
    assert len(montants) == 3 and all(m > 0 for m in montants), \
        "REGIME DEGENERE : montants non-bloques = %s -- l'accord ne prouverait rien" % (montants,)
    assert len(set(montants)) == 3, \
        "REGIME DEGENERE : deux rangs prennent le MEME montant (%s) -- un splash serait " \
        "indiscernable d'une vague" % (montants,)
    assert sorted(vague["off_delta"].items()) == sorted(vague["live_delta"].items()), \
        "degat port != natif : %s vs %s" % (sorted(vague["off_delta"].items()),
                                            sorted(vague["live_delta"].items()))


def test_slashing_dive_montants_decroissants_par_rang(vague):
    """Le montant est INDEXE PAR RANG, et les `dmg` de 1091 sont strictement DECROISSANTS : les
    montants infliges doivent l'etre aussi. Un port qui figerait un seul montant (au lieu d'indexer
    `dmg[i]`) rendrait trois valeurs EGALES, alors meme que le total resterait plausible."""
    dmg = vague["damages_config"]
    assert len(dmg) == 3 and dmg[0] > dmg[1] > dmg[2], \
        "la config de 1091 n'est plus strictement decroissante (%s) : la garde ne mord plus" % (dmg,)
    montants = [m for m, _b in vague["rangs"]]
    assert montants[0] > montants[1] > montants[2], \
        "les montants natifs ne suivent pas l'ordre des rangs : %s" % (montants,)
    ratios = [r for r in P._ratios(vague["rangs"], dmg) if r is not None]
    assert len(ratios) == 3 and max(ratios) - min(ratios) < 0.01, \
        "le ratio montant/dmg DERIVE selon le rang (%s) : le montant n'est pas indexe par rang" \
        % (ratios,)


def test_slashing_dive_famille_ability_donc_aucun_crit(vague):
    """`DSLBehaviors$$AbilityDamage` -> `AbilityDamageOperation` : cette famille n'a AUCUN slot
    `RollCritical`. Le natif ne crit donc JAMAIS sur cette vague -- c'est un OBSERVABLE, et c'est
    ce qui distingue la route portee de la famille ATTACK (qui crit et consomme 2 tirages/coup)."""
    assert vague["live_crit"], "aucun coup mesure : la garde ne mord pas"
    assert all(c == 0 for c in vague["live_crit"]), \
        "le natif a CRIT sur une attaque d'ability : %s" % (vague["live_crit"],)


def test_slashing_dive_profil_de_degat_est_celui_de_SA_config(vague):
    """`pierce` SEPARE, et c'est la garde qui SEPARE 1091 DE SA SOEUR : le `DamageProfileType` de
    CHAQUE coup natif == l'ordinal du profil lu au gameconfig POUR 1091 (`Power`), qui n'est PAS
    celui de 1064 (`Piercing`). Recopier la constante de la voisine tombe ici."""
    from engine.runner.abilities.aeldari import swooping_hawk_profile
    from engine.runner.abilities.thousandsons import slashing_dive_profile
    attendu = P.profil_ordinal()
    assert attendu >= 0, "le profil de 1091 ne resout pas dans PROFILE_NAME_BY_INDEX"
    assert slashing_dive_profile() != swooping_hawk_profile(), \
        "1091 et 1064 auraient le MEME profil : la garde ne discriminerait plus les deux configs"
    assert vague["live_profile"] == [attendu], \
        "profil natif %s != %s (config de 1091)" % (vague["live_profile"], attendu)


def test_slashing_dive_atterrit_derriere_la_derniere_cible(vague):
    """L'ATTERRISSAGE, branche VRAIE : le caster finit sur la tuile un pas AU-DELA du dernier rang
    touche. C'est aussi ce qui refute l'ordre d'arguments inverse de
    `TileBehindTargetFromSourceDirection` -- la tuile « devant » serait entre le caster et sa
    cible, dans l'autre sens."""
    assert vague["live_caster_pos"][1] == P.LANDING_TILE, \
        "le NATIF n'atterrit pas derriere le 3e rang : %s" % (vague["live_caster_pos"],)
    assert vague["off_caster_pos"][1] == vague["live_caster_pos"][1], \
        "position finale port != natif : %s vs %s" % (vague["off_caster_pos"][1],
                                                      vague["live_caster_pos"][1])


def test_slashing_dive_repli_quand_la_tuile_est_occupee(repli):
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


def test_slashing_dive_ancre_sur_la_derniere_tuile_OCCUPEE(ancre):
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


def test_slashing_dive_letal_les_trois_meurent_et_l_ancre_reste_figee(letal):
    """LETALITE + ancre figee AU CAST. Le natif EVALUE les trois selecteurs A LA CONSTRUCTION du
    behaviour, avant tout degat : la 3e tuile compte comme « derniere cible touchee » meme si son
    occupant meurt du premier coup. Le caster atterrit donc derriere un CADAVRE.

    ⚠ Le montant NATIF est ici CLAMPE aux PV restants (le tag `Amount` vaut 900 pour les trois),
    alors que le port rapporte le montant CALCULE. On confronte donc les DELTAS de PV et l'ensemble
    des MORTS -- les deux oracles de la letalite -- pas les montants bruts."""
    assert letal["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"
    assert len(letal["live_morts"]) == 3, \
        "le scenario LETAL ne tue pas les trois cibles : %s" % (letal["live_morts"],)
    assert letal["off_morts"] == letal["live_morts"], \
        "l'ensemble des MORTS differe : port %s vs natif %s" % (letal["off_morts"],
                                                                letal["live_morts"])
    assert sorted(letal["off_delta"].items()) == sorted(letal["live_delta"].items()), \
        "degat port != natif : %s vs %s" % (sorted(letal["off_delta"].items()),
                                            sorted(letal["live_delta"].items()))
    assert letal["live_caster_pos"][1] == P.LANDING_TILE, \
        "le NATIF n'ancre plus sur la 3e tuile alors que son occupant est mort : %s" \
        % (letal["live_caster_pos"],)
    assert letal["off_caster_pos"][1] == letal["live_caster_pos"][1], \
        "position finale port != natif : %s vs %s" % (letal["off_caster_pos"][1],
                                                      letal["live_caster_pos"][1])


def test_slashing_dive_un_rang_bloque_est_suivi_par_le_port(bloque):
    """LE BLOCK, l'autre face de l'etage degat. Sous ce MT le 2e rang BLOQUE : montant natif 0 et
    AUCUN PV perdu. Le port doit rendre exactement cela -- un port qui ignorerait le block
    infligerait le montant plein et ne se verrait dans AUCUN autre scenario du fichier."""
    assert bloque["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"
    assert any(b for b in bloque["live_block"]), \
        "AUCUN rang ne bloque sous ce MT : la garde ne mord pas (le scenario a perdu son objet)"
    bloques = [m for m, b in bloque["rangs"] if b]
    assert bloques and all(m == 0 for m in bloques), \
        "un rang BLOQUE inflige quand meme du degat cote natif : %s" % (bloques,)
    assert sorted(bloque["off_wave"]) == sorted(bloque["live_wave"]), \
        "vague port != natif sous block : %s vs %s" % (bloque["off_wave"], bloque["live_wave"])
    assert sorted(bloque["off_delta"].items()) == sorted(bloque["live_delta"].items()), \
        "degat port != natif sous block : %s vs %s" % (sorted(bloque["off_delta"].items()),
                                                       sorted(bloque["live_delta"].items()))


def test_slashing_dive_gate_de_ciblage_mord(vague):
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


def test_slashing_dive_masque_a_une_seule_source():
    """CONTRAT DE DISJONCTION : 1091 est au registre, donc son masque vit sur SA classe et NULLE
    PART ailleurs. Deux sources divergeraient en silence. Cette garde vaut AUSSI pour le litteral
    `AbilityAttackType`, l'autre donnee obligatoire du registre."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
    assert SLASHING_DIVE in ABILITY_CLASSES, "1091 n'est pas au registre"
    assert SLASHING_DIVE not in TARGETING_OPTIONS_UNPORTED, \
        "1091 a DEUX sources de masque (registre + TARGETING_OPTIONS_UNPORTED)"
    assert getattr(ABILITY_CLASSES[SLASHING_DIVE], "TARGETING_OPTIONS", None) is not None, \
        "1091 est au registre SANS masque -- gate permissif silencieux"
    assert SLASHING_DIVE in ABILITY_ATTACK_TYPE, \
        "1091 est au registre SANS son litteral AbilityAttackType"


def test_slashing_dive_partage_la_base_avec_swooping_hawk():
    """LE PARTAGE, garde OFFLINE : les deux heritieres sont la MEME classe de base portee, et elles
    ne different QUE par leur identite et leurs deux donnees de registre.

    C'est le pendant statique de la mesure runtime (`resolveMethodPtr` : `.ctor` a la meme adresse
    d'entree, aucune surcharge a depth=0). Si un jour l'une des deux avait besoin d'un
    `execute_behaviour` propre, ce test rougirait -- et ce serait la bonne reaction : le natif, lui,
    n'en a pas."""
    from engine.runner.abilities.aeldari import SwoopingHawkAbility
    from engine.runner.abilities.loki.dive_attack import DiveAttackAbility
    from engine.runner.abilities.thousandsons import SlashingDiveAbility
    assert issubclass(SlashingDiveAbility, DiveAttackAbility)
    assert issubclass(SwoopingHawkAbility, DiveAttackAbility)
    for cls in (SlashingDiveAbility, SwoopingHawkAbility):
        assert "execute_behaviour" not in vars(cls), \
            "%s surcharge `execute_behaviour` : le natif ne surcharge RIEN" % cls.__name__
    assert SlashingDiveAbility.ABILITY_TYPE != SwoopingHawkAbility.ABILITY_TYPE
    assert SlashingDiveAbility.ABILITY_ID != SwoopingHawkAbility.ABILITY_ID
