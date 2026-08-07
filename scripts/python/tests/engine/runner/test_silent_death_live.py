"""CONFRONT LIVE de `1068 SilentDeath` (`eldarJainZar` Jain Zar, Aeldari, HERO) -- #497.

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * la TOPOLOGIE de la chaine. Le decompile de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour` construit
    ses maillons PAR UNE BOUCLE, et le pool du maillon `i` est
    `AdjacentUnits(maillon i-1) & <cache ennemis> - <deja frappes>` : c'est le PRECEDENT, pas la
    cible. Le patron voisin de ce meme module (splash `HarvesterOfSouls` : ennemis adjacents A LA
    CIBLE) donnerait un ensemble DIFFERENT des le 2e maillon. Le montage aligne QUATRE ennemis en
    colonne, donc le 4e est a 3 hex de la cible : un port « splash » ne peut pas l'atteindre.
  * le CARDINAL. `nrOfTargets` compte les maillons ADDITIONNELS -- le total frappe est
    `1 + nrOfTargets`. Lire la constante comme un total ferait perdre un maillon, silencieusement.
  * le DEGAT COUP PAR COUP, `state.rng` CALE sur le MT live. C'est ce qui DECOMPOSE la mecanique
    `pierce` du kit (profil `Piercing` -> `PiercingRatio` -> armure) au lieu de l'absorber dans un
    total : un total juste peut cacher deux etages faux qui se compensent.
  * le TIRAGE. Sur la variante `branche`, les pools ont 3 puis 2 candidats -> le
    `PickRandomly(pool, 1)` est un VRAI tirage et l'ordre de la chaine est decide par le PRNG. Le
    montage nominal a des pools SINGLETON : il ne peut pas separer « le port tire au bon moment »
    de « le port ne tire pas du tout ».
  * le GATE DE CIBLAGE. `TARGETING_OPTIONS` absent => `get_invalid_target_reason` rend 0
    immediatement : le moteur accepterait des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Degradation PERMISSIVE,
    ni erreur ni crash, invisible en self-play -- exactement le trou qu'un entrainement exploiterait.
  * le CONTRAT DE DISJONCTION. Une ability portee porte son masque sur SA classe, jamais dans
    `TARGETING_OPTIONS_UNPORTED` : deux copies divergeraient en silence.

RESIDU HERITE, MESURE et NON GARDE ICI (`#497-r1`) : l'adjacence du runner
(`engine/dsl/base.py::_within`) teste `hexgeo.distance <= r` alors que le natif enumere la liste
d'adjacence STOCKEE (porte `|dElev| < 2`). Sur MC1_67 la couronne hex SUR-ATTEINT la liste native de
**18 aretes dirigees sur 316**, et la chaine de 1068 y devient LONGUE DE 4 la ou le natif s'arrete a
1. Aucun test n'est ecrit dessus : un test qui ASSERTE la divergence figerait le bug. La mesure vit
dans `probe_497_silent_death.py --variantes` (variante `elevation`), etage [6].

Le montage (build + DRIVE des positions par `--place`/`--a-place`, tuiles CHOISIES sur les
elevations) et TOUTES les lectures vivent dans `scripts/python/probe_497_silent_death.py` : le probe
MESURE, ce test GARDE, une seule implementation -- aucune divergence possible entre les deux.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee hors du montage, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_497_silent_death as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE, pas une facilite : ce fichier importe le PROBE, qui
    # importe `ABILITY_CLASSES` -- sa fermeture d'import atteint la quasi-totalite de
    # `scripts/python` (mesure de #491 sur le meme patron : 144 chemins lus/importes hors d'un
    # perimetre « evident » de 14 modules, dont `board.py`, `catalog_inject.py` et tout
    # `engine/ai/`). Declarer etroit produirait un FAUX VERT : le test ne serait pas rejoue quand ce
    # qu'il mesure change.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle des sept gardes (topologie, cardinal, degat coup par coup, tirage,
    # gate) : un changement de build peut les faire changer d'avis sans qu'une ligne du port bouge.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de 1068. Le verdict depend du code du port (arbre "
              "DSL de la chaine + selecteurs d'adjacence/pick/cache + la feuille d'attaque + le "
              "registre + le masque de ciblage), du MONTAGE (le probe, qui porte le drive des "
              "positions choisi sur les ELEVATIONS et TOUTES les lectures), des entrees versionnees "
              "du runner, et du BUILD charge -- l'oracle etant le jeu lui-meme, pas une constante "
              "ecrite ici. Le perimetre est pris a tout `scripts/python` parce que la fermeture "
              "d'import du probe y atteint des chemins qu'aucune liste explicite n'aurait devines.",
}

SILENT_DEATH = P.SILENT_DEATH                    # 1068 ActiveAbilityType.SilentDeath


@pytest.fixture(scope="module")
def chaine(live_session):
    """UN SEUL runner pour le montage NOMINAL : le cast est joue une fois des DEUX cotes, les gardes
    ci-dessous relisent la MEME mesure (le cast n'est pas rejouable -- il consomme l'actif)."""
    m, dispose = P.measure(live_session, state_name="test_497_chaine")
    try:
        yield m
    finally:
        dispose()


@pytest.fixture(scope="module")
def branche(live_session):
    """UN SECOND runner, geometrie BRANCHUE : les pools des maillons ont 3 puis 2 candidats, donc le
    `PickRandomly(pool, 1)` natif est un VRAI tirage. Sans lui, toutes les gardes de ce fichier
    tiendraient sur des pools SINGLETON, ou « tirer » et « prendre l'unique element » sont
    indiscernables."""
    nom, ctile, places, hp = P.VARIANTES[0]
    assert nom == "branche", "la 1re variante du probe n'est plus `branche` (%s)" % nom
    m, dispose = P.measure_montage(live_session, ctile, places, hp,
                                   state_name="test_497_branche")
    try:
        yield m
    finally:
        dispose()


def test_silent_death_execution_est_portee(chaine):
    """La face EXECUTION est portee : sans elle, la decision CHOISIT le cast et l'execution
    l'IGNORE -- 0 degat, 0 effet, AUCUNE erreur (le no-op silencieux que #497 ferme)."""
    assert chaine["routed"] == "handler" and chaine["ported"] is True, \
        "1068 non portee (routed=%s ported=%s)" % (chaine["routed"], chaine["ported"])
    assert not chaine["cast_error"], "cast natif bloque: %s" % chaine["cast_error"]
    assert chaine["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"


def test_silent_death_chaine_part_du_maillon_precedent(chaine):
    """LA garde de topologie : la suite ORDONNEE des cibles, port == natif == la colonne montee.

    Le 4e maillon est a TROIS hex de la cible primaire : un port qui prendrait « les ennemis
    adjacents A LA CIBLE » (patron splash `HarvesterOfSouls`, meme module) ne pourrait pas
    l'atteindre. C'est ce qui separe les deux modeles, et rien d'autre ne le separe."""
    assert chaine["live_chain"] == chaine["attendu"], \
        "le NATIF ne suit pas la colonne montee: %s != %s" % (chaine["live_chain"],
                                                              chaine["attendu"])
    assert chaine["off_chain"] == chaine["live_chain"], \
        "chaine PORT %s != chaine NATIF %s" % (chaine["off_chain"], chaine["live_chain"])
    import hexgeo
    d = hexgeo.distance(P.CHAIN_TILES[0], P.CHAIN_TILES[-1])
    assert d >= 3, ("le montage ne SEPARE plus chaine et splash : dernier maillon a %d hex de la "
                    "cible (il en faut >= 3, sinon un splash ring-1 l'atteindrait)" % d)


def test_silent_death_cardinal_est_un_plus_nr_of_targets(chaine):
    """`nrOfTargets` compte les maillons ADDITIONNELS (i2 : « and up to N ADDITIONAL enemies ») :
    le total frappe est `1 + nrOfTargets`. Le lire comme un total perdrait un maillon."""
    from engine.runner.abilities.aeldari import silent_death_num_targets
    n = silent_death_num_targets()
    assert n >= 1, "nrOfTargets illisible dans le gameconfig (%r) -- garde sans objet" % n
    assert len(chaine["live_chain"]) == 1 + n, \
        "le NATIF frappe %d unites pour nrOfTargets=%d" % (len(chaine["live_chain"]), n)
    assert chaine["max_targets"] == 1 + n


def test_silent_death_degat_coup_par_coup_bit_exact(chaine):
    """`state.rng` CALE sur le MT live -> egalite BIT-EXACTE des `per_hit` de CHAQUE maillon.

    On compare la SUITE des coups, pas le total : un total juste peut cacher deux etages faux qui
    se compensent (bornes trop hautes x percage trop bas). Et on exige un temoin NON NUL -- un
    accord sur `[]` == `[]` ne prouverait rien."""
    from engine.runner.abilities.aeldari import SILENT_DEATH_ID
    from engine.entities.effects.magnitude import ability_var
    n_hits = int(ability_var(SILENT_DEATH_ID, "nrOfHits", is_constant=True) or 0)
    assert n_hits >= 1
    for uid in chaine["live_chain"]:
        natif = chaine["live_per_hit"].get(uid)
        port = chaine["off_per_hit"].get(uid)
        assert natif and all(x is not None and x > 0 for x in natif), \
            "regime DEGENERE sur %d : le natif n'a inflige aucun degat (%s)" % (uid, natif)
        assert len(natif) == n_hits, \
            "le natif a porte %d coups sur %d, nrOfHits=%d" % (len(natif), uid, n_hits)
        assert port == natif, "coup par coup sur %d : port=%s natif=%s" % (uid, port, natif)
    assert chaine["off_delta"] == chaine["live_delta"], \
        "totaux port=%s natif=%s" % (chaine["off_delta"], chaine["live_delta"])


def test_silent_death_groupe_damage_chain(chaine):
    """`Group(..., 0x1d)` du decompile = `GroupType.DamageChain` (membre LU dans
    `data/symbols/<build>/frida/enums.tsv`). La cascade native doit en porter EXACTEMENT un -- c'est
    la confirmation live du litteral, et le seul canal qui le publie."""
    from engine.streams.group_type import GroupType
    from engine.runner.abilities.aeldari import SILENT_DEATH_GROUP
    assert int(SILENT_DEATH_GROUP) == int(GroupType.DamageChain) == P.GROUP_DAMAGE_CHAIN
    assert chaine["n_chain_groups"] == 1, \
        "cascade native : %d groupe(s) DamageChain (attendu 1)" % chaine["n_chain_groups"]


def test_silent_death_gate_de_ciblage_mord(chaine):
    """`TargetIsEnemy` (0x4000) est le SEUL bit du preset `+0x40`. Le port doit refuser l'allie et
    le self AVEC CE CODE, et accepter l'ennemi -- et l'oracle du refus est le natif lui-meme
    (`abilityTargets.targets`, superset move-inclus, n'enumere que des ennemis).

    ⚠ Le code de refus se CITE par son membre, jamais par sa valeur : une constante `0x4000`
    ecrite ici serait une SECONDE source pour la meme information, que rien n'obligerait a suivre
    le dump (cliquet `test_ability_registry_ratchet.py`, qui a mordu sur ce fichier)."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    g = chaine["gate"]
    assert g["ennemi"] == 0, "le port REFUSE une cible que le natif accepte (code %s)" % g["ennemi"]
    assert g["allie"] == int(TR.TargetIsEnemy), \
        "allie: le port rend %s, attendu TargetIsEnemy" % g["allie"]
    assert g["soi"] == int(TR.TargetIsEnemy), \
        "soi: le port rend %s, attendu TargetIsEnemy" % g["soi"]
    assert chaine["gate_natif"]["allie_dans_targets"] is False
    assert chaine["gate_natif"]["soi_dans_targets"] is False


def test_silent_death_tirage_aleatoire_accorde(branche):
    """Le `PickRandomly(pool, 1)` est EXERCE (pools de 3 puis 2 candidats) et le port pique le MEME
    element que le natif, DANS LE MEME ORDRE.

    Le temoin de non-degenerescence est que l'ordre obtenu N'EST PAS l'ordre des ids : s'il l'etait,
    un port qui prendrait « le premier du pool » passerait sans jamais tirer."""
    assert branche["off_chain"] == branche["live_chain"], \
        "ordre PORT %s != ordre NATIF %s" % (branche["off_chain"], branche["live_chain"])
    assert len(branche["live_chain"]) >= 3, \
        "la geometrie branchue n'a pas produit de chaine (%s)" % branche["live_chain"]
    assert branche["live_chain"] != sorted(branche["live_chain"]), \
        ("l'ordre natif coincide avec l'ordre des ids (%s) : le tirage n'est PAS exerce, la garde "
         "passerait sur un port qui prend toujours le premier" % branche["live_chain"])
    for uid in branche["live_chain"]:
        assert branche["off_per_hit"].get(uid) == branche["live_per_hit"].get(uid), \
            "coup par coup sur %d : port=%s natif=%s" % (uid, branche["off_per_hit"].get(uid),
                                                         branche["live_per_hit"].get(uid))


def test_silent_death_registre_porte_ses_deux_donnees_et_le_masque_a_migre():
    """OFFLINE (aucun runner) -- les deux donnees obligatoires du registre et le CONTRAT DE
    DISJONCTION.

    `TARGETING_OPTIONS` absent => aucun gate ; `ABILITY_ATTACK_TYPE` absent => `HasAttackType` rend
    False et les triggers `On(PreUnitAbility)` gates dessus se taisent. Les deux degradations sont
    SILENCIEUSES. Et le masque doit vivre sur la classe, PAS dans `TARGETING_OPTIONS_UNPORTED` :
    deux copies divergeraient sans que rien ne le dise."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    klass = ABILITY_CLASSES.get(SILENT_DEATH)
    assert klass is not None, "1068 absente d'ABILITY_CLASSES -> NO-OP SILENCIEUX"
    opts = klass.TARGETING_OPTIONS
    assert opts is not None, "1068 au registre SANS son masque -> gate de cible DESARME"
    assert int(opts.rules) == int(TR.TargetIsEnemy), \
        "masque 1068 = %s, attendu TargetIsEnemy SEUL (preset statique +0x40)" % opts.rules
    assert opts.self_cast is False
    assert ABILITY_ATTACK_TYPE.get(SILENT_DEATH) == AbilityAttackType.DirectTargetAttack, \
        "1068 sans son litteral AbilityAttackType (3e arg d'AActiveAbility$$.ctor)"
    assert SILENT_DEATH not in TARGETING_OPTIONS_UNPORTED, \
        "1068 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (contrat de disjonction rompu)"
