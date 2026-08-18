"""#933 -- CLIQUET : une premisse de REGIME se DECLARE au montage, elle ne se suppose pas.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE
-----------------------------------------------
La bascule #419-r5/-r6 (items Best-In-Slot equipes par defaut) a peri des dizaines de premisses
de test SANS qu'une ligne de moteur bouge : `could_crit` est passe de 0/106 a 98/106, et 46 des
106 unites ont gagne une base de block. Cinq victimes ont ete trouvees, dont TROIS PAR HASARD en
jouant une regression sans rapport, et une (`test_lion_helm_block_aura_live`) est restee ROUGE
sur `master` pendant cinq jours en accusant le SELECTEUR au lieu du regime.

Le mode de defaillance n'est pas « un test casse » -- c'est **une prose qui cesse d'etre vraie
sans que rien ne l'evalue**. #914 §4.1 l'avait nomme sans l'outiller : « une premisse en
commentaire n'est PAS executable ; la seule chose qui l'a signalee, c'est un test qui rougit des
mois plus tard en accusant le port ». Ce fichier est cette chose executable.

L'INVARIANT, en un mot : un test LIVE qui LIT une stat a zero ouvert (`CritChance`, `CritDamage`,
`BlockChance`, `BlockDamage` -- les quatre dont une unite passe de 0 a non-0 sous la bascule) et
qui COMPARE a zero / a un positif doit NEUTRALISER cette base au montage
(`--unit-stat <u>:<Stat>=0`, ou les DEUX faces de `--crit`/`--crit-target`, resp.
`--block-player`/`--block-target`). Les fichiers qui ne le font pas sont ENUMERES ci-dessous,
mesures un par un ; le cliquet interdit que la liste GRANDISSE.

Ce n'est pas une allowlist de complaisance : un fichier REPARE en SORT, donc perdre son montage
le fait revenir dans `nouveaux` et ROUGIR. C'est le cran qui manquait -- `probe_419r6` ne voyait
que les fichiers exigeant un coup propre ou portant une valeur en dur, et `test_lion_helm...`
n'etait ni l'un ni l'autre.

⚠ `_ATTESTES` est une DETTE INVENTORIEE, pas un blanc-seing : y figurer ne dit PAS que la
premisse du fichier tient, seulement qu'elle n'etait pas declaree au moment de #933 et qu'elle
n'a pas ete tranchee. Le seul engagement du cliquet est que cette liste ne GRANDISSE pas.
Exemple vecu : `test_928_legacy_of_combat_live.py` y est entre AU REBASE de #933 -- il est arrive
par un merge pendant la tranche, sa docstring porte bien une premisse de regime
(« 2 tirages chacun a `critChance = 0` »), et il n'a PAS ete mesure ici.

⚠ `TACTICUS_BIS_ITEMS=0` est un instrument de DIAGNOSTIC, jamais un remede : il deshabille tout
le roster et restitue le regime DEGENERE que #419-r6 a supprime (cf. #914 §3.3).

REGENERER la liste : `python scripts/python/probe_933_premisses_regime.py --attester`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

import probe_933_premisses_regime as P                               # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # Le recenseur sous test : son jeu de stats, ses marqueurs de neutralisation et ses
        # regles de classement live/offline decident A EUX SEULS du verdict.
        "scripts/python/probe_933_premisses_regime.py",
        # Le foyer des leviers de montage que le cliquet exige : si `--unit-stat` / `--crit` /
        # `--block-*` cessaient d'ECRIRE la base du BC, la neutralisation deviendrait fictive et
        # ce cliquet passerait au vert sur des montages inoperants.
        "scripts/python/rl_duel.py",
        # La bascule elle-meme (`_EQUIP_ITEMS_PAR_DEFAUT`, `_bis_item_specs`) : c'est elle qui
        # definit QUELLES stats sont a zero ouvert.
        "scripts/python/rl_collect_batch.py",
    ),
    "build": False,
    # `toujours: False` -- la cle est OBLIGATOIRE, et `probe_486r15` refuse le couple
    # (`toujours: True` + `hors_confrontation`) comme SANS OBJET. C'est donc le bypass qui porte
    # l'impossibilite de borner, et la selection se fait par `chemins` : ce dont le VERDICT depend.
    "toujours": False,
    "raison": "Le perimetre de ce cliquet est DERIVE de tout `scripts/python/tests/**/test_*.py` "
              "(rglob) : n'importe quel fichier de test ajoute, renomme ou dont le montage change "
              "peut entrer ou sortir de la liste des suspects. Un declencheur par chemins ne peut "
              "donc pas etre a la fois juste et etroit -- et c'est exactement le gisement que ce "
              "cliquet garde : les prochaines victimes seront des fichiers qui n'existent pas "
              "encore.",
    # REGIME BALAYAGE (#486-r24) -- pose au MERGE, pas par l'auteur. `probe_486r15` rendait ROUGE
    # << DECLARE TROP ETROIT : 10 chemin(s) lu(s)/importe(s) hors du perimetre declare >>, les 10
    # etant des FICHIERS DE TEST que l'etage d'inventaire ouvre en les rglobant. La raison ci-dessus
    # etablissait deja l'impossibilite d'enumerer ; il lui manquait la cle qui la rend COMPTEE et
    # ATTESTEE. Meme regime, et pour la meme cause, que les 4 balayeurs deja declares
    # (`457_r8`, `464`, `485r2`, `486r24`) : ce qu'ils LISENT est le parc entier.
    # Le bypass n'est pas gratuit -- un bypass qui ne masque AUCUN decouvert est lui-meme un ROUGE.
    "hors_confrontation":
        "Il BALAIE le parc de TESTS : l'etage d'inventaire rglobe `scripts/python/tests/**/"
        "test_*.py` et OUVRE chaque fichier pour y chercher une premisse de regime. Aucune "
        "enumeration ne peut le borner, par construction -- le gisement qu'il garde est fait des "
        "fichiers qui n'existent pas encore. Ce dont son VERDICT depend est nomme dans `chemins` "
        "(le recenseur, le foyer des leviers de montage, la bascule BiS) ; ce qu'il LIT est le parc.",
}


# --- BLOC GENERE (`probe_933_premisses_regime.py --attester`) -- ne pas tenir a la main -------
# ⚠ 8 CHEMINS EN SONT SORTIS le 2026-08-18 (#10027), et c'est un RENFORCEMENT, pas un
# relachement : le recenseur ne lisait le montage que dans le FICHIER DE TEST, alors que 9
# suspects sur 39 portent leur `--unit-stat`/`--crit`/`--block-*` dans un module IMPORTE. Ils ne
# sont plus suspects parce que leur montage a ete LU, pas parce qu'on l'a excuse -- et sortir de
# cette liste les fait passer du regime « dette toleree » au regime « si le levier disparait, le
# cliquet ROUGIT ». `test_la_liste_attestee_est_encore_ACCUSEE` garde cette propriete pour toutes
# les entrees restantes.
_ATTESTES = (
    # ⚠ ENTRE AU REBASE DE #933-r4, exactement comme `test_928_legacy_of_combat_live.py` avant lui :
    # il est arrive par un merge pendant la tranche (`#966-r3`, `1212 HealingBalms`), il LIT
    # `critchance`/`critdamage` et neutralise `Armor`/`FixedArmor`/`Health` mais AUCUNE des quatre
    # stats a zero ouvert -- et il est suspect AVEC comme SANS le critere (C) ajoute par #933-r4
    # (mesure : `attendu-positif`, `attendu-non-nul`, `valeur-en-dur` suffisent). Il n'a donc PAS
    # ete mesure ici, et l'inscrire ne dit rien de la tenue de sa premisse.
    "engine/test_966r3_execution_du_cast_live.py",
    "engine/runner/test_448r2dr2_titanhammer_active_live.py",
    "engine/runner/test_503r1_overwhelming_wrath_phase2_live.py",
    "engine/runner/test_895_nova_boss_riptide_live.py",
    "engine/runner/test_919_icon_of_obstinacy_live.py",
    "engine/runner/test_beast_slayer_block_live.py",
    "engine/runner/test_beast_slayer_extradmg_live.py",
    "engine/runner/test_case231_charge_forcecrit_live.py",
    "engine/runner/test_daemon_extra_block_live.py",
    "engine/runner/test_heroic_fusillade_migration_live.py",
    "engine/runner/test_lion_helm_overwatch_aura_live.py",
    "engine/runner/test_mow_caster_load_live.py",
    "engine/runner/test_mow_groups_bcd_live.py",
    "engine/runner/test_overkill_decision_live.py",
    "engine/runner/test_overkill_gate_live.py",
    "engine/runner/test_path_of_command_crit_aura_live.py",
    "engine/runner/test_prevent_overkill_decision_live.py",
    "engine/runner/test_rad_bombardment_live.py",
    "engine/runner/test_reinforced_hive_node_live.py",
    "engine/runner/test_shield_ability_limits_live.py",
    "engine/runner/test_spirit_leech_combat_live.py",
    "engine/runner/test_summon_spawn_live.py",
    "engine/runner/test_thrill_seekers_live.py",
    "engine/test_419r5_canal_crit_ouvert_live.py",
    "engine/test_890_hive_tyrant_live.py",
    "engine/test_healing_balms_heal_decision_live.py",
    "engine/test_min_distance_move_leaf_live.py",
)
# --- FIN DU BLOC GENERE -----------------------------------------------------------------------

#: LES FAUX POSITIFS **MESURES** -- distincts d'`_ATTESTES`, et la distinction est le point.
#: `_ATTESTES` dit « pas tranche » ; ceci dit « tranche, le RECENSEUR a tort », avec la mesure.
#: Les trois sont entres ensemble (#10027), tous les trois accuses par le meme rouge, et pour
#: **trois causes differentes** -- ce qui est exactement pourquoi aucune regle statique ne les
#: sort tous les trois.
#:
#:   * `test_1001_votann_relics_live.py` -- il ECRIT son regime crit
#:     (`probe_1001_votann_relics.py` : `--unit-stat votanUthar:CritChance=<100 si reset sinon 0>`,
#:     avec la raison au site) mais n'ecrit pas `CritDamage`, que `_stats_concernees` exige EN
#:     PAIRE. Or le fichier ne mesure AUCUN jet de critique : il compare des **DELTAS** de stat
#:     (`native_delta`, `cc_delta`, `cd_delta`), invariants par translation de la base BiS. Sa
#:     docstring le dit : « On ne mesure AUCUN jet de critique -- on lit les STATS ».
#:     ⚠ La regle « une stat de la paire suffit » a ete ECARTEE : `ForceCrit` (trait `Charge`,
#:     cf. `test_case231_charge_forcecrit_live.py`) fait critter A `CritChance = 0`, donc la
#:     chance ne rend PAS le degat inerte, et l'exigence de paire est JUSTE en general.
#:   * `test_1009_reliques_dark_angels_live.py` -- il ne LIT PAS la stat `BlockChance`. La
#:     detection est une SOUS-CHAINE (`_lit_stats` cherche `blockchance` dans la source en
#:     minuscules) et elle mord sur `BlockChanceInfo` -- le champ `entityId` de l'effet 1540, et
#:     sur la variable de gameconfig `blockChance`, dont le fichier dit lui-meme qu'elle est
#:     « CONSTANTE (10) sur les dix paliers ». Ses assertions accusees portent sur des ids et des
#:     paliers de config (`== 10`, `== 1540`, `== 50`, `== "MonsterSlayerOfCaliban"`).
#:     ⚠ Le remede evident -- une FRONTIERE DE MOT sur `_lit_stats` -- a ete MESURE et ECARTE :
#:     il fait perdre le statut de lecteur a **7 fichiers** (dont `test_895_nova_boss_riptide`,
#:     `test_additional_hits_roll_order`, `test_healing_balms_heal_decision`), donc il RETRECIT la
#:     population du recenseur au lieu d'affiner son critere. Residu `#10027-r1`.
#:   * `test_martial_apotheosis_live.py` -- il EXERCE le regime crit au lieu de le supposer nul :
#:     il derive une bande PAR REGIME (`[bmin+cd, bmax+cd]` si le coup crite) et porte un garde de
#:     non-degenerescence `assert cd > 0` avec sa raison ecrite. **Le remede prescrit par le
#:     cliquet (`--unit-stat <u>:CritDamage=0`) le rendrait ROUGE par cette assertion meme** --
#:     c'est le renversement complet, et aucune liste ne doit le pousser vers ce montage.
_FAUX_POSITIFS_MESURES = (
    "engine/runner/test_1001_votann_relics_live.py",
    "engine/runner/test_1009_reliques_dark_angels_live.py",
    "engine/runner/test_martial_apotheosis_live.py",
)


_CACHE_SUSPECTS: dict = {}


def _suspects_courants() -> set[str]:
    """Memoise : le recensement balaie ~900 fichiers et DEUX tests l'exigent desormais."""
    if "v" not in _CACHE_SUSPECTS:
        _CACHE_SUSPECTS["v"] = set(P._suspects(P.recenser()))
    return _CACHE_SUSPECTS["v"]


def test_le_jeu_de_stats_est_coherent_et_non_vide():
    """Les 4 stats a ZERO OUVERT sont un SOUS-ENSEMBLE des sensibles, et chacune est NOMMABLE.

    Un jeu vide, ou une stat sans mot de correspondance, rendrait le recenseur muet SANS que rien
    ne le dise -- exactement le vice « un recenseur ne peut pas rendre zero sur ce qu'il ne visite
    pas ». On assertionne donc son propre non-vide.
    """
    assert P._STATS_ZERO_OUVERT, "jeu de stats a zero ouvert VIDE : le recenseur ne voit rien"
    assert set(P._STATS_ZERO_OUVERT) <= set(P._STATS_SENSIBLES)
    for stat in P._STATS_ZERO_OUVERT:
        assert P._MOTS_PAR_STAT.get(stat), \
            "%s n'a aucun mot de correspondance : elle ne sera nommee nulle part" % stat
    assert P._LECTURES_ZERO_OUVERT, "aucun nom de LECTURE : aucun fichier ne sera classe lecteur"


def test_le_recenseur_voit_la_victime_connue(tmp_path):
    """ANTI-TAUTOLOGIE : sur un arbre TEMOIN, le recenseur DOIT classer suspect le patron exact de
    `test_lion_helm_block_aura_live.py` d'avant reparation -- une comparaison a `(0, 0)` dont
    AUCUN mot de l'expression ne nomme la stat (elle n'est nommee que par la fonction qui a
    produit la valeur). La premiere ecriture du recenseur exigeait que l'expression nomme la stat
    et ratait donc son propre cas d'entree ; un recenseur qui ne voit pas la victime CONNUE ne
    peut rien dire des inconnues.

    Second bras, indispensable : la MEME source, une fois NEUTRALISEE au montage, ne doit PLUS
    etre suspecte. Sans lui, un recenseur qui rendrait « suspect » pour tout passerait ce test.
    """
    nu = (
        'BUILD = ["--p-units", "darkaAzrael"]\n'
        'def _live_blocks(rpc, rid):\n'
        '    return {u["entityId"]: (u["stats"]["blockChance"], u["stats"]["blockDamage"])\n'
        '            for u in rpc("combatSnapshot")["units"]}\n'
        'def test_x(build_runner):\n'
        '    seed = _live_blocks(None, 0)\n'
        '    assert seed[az] == (0, 0), "le PORTEUR se self-buffe"\n'
    )
    neutre = nu.replace(
        'BUILD = ["--p-units", "darkaAzrael"]',
        'BUILD = ["--p-units", "darkaAzrael",\n'
        '         "--unit-stat", "darkaAzrael:BlockChance=0,BlockDamage=0"]')

    (tmp_path / "test_temoin_nu_live.py").write_text(nu, encoding="utf-8")
    rec = P.recenser(tmp_path)
    susp = P._suspects(rec)
    assert "test_temoin_nu_live.py" in susp, (
        "le recenseur NE VOIT PAS le patron de la victime connue -- il ne garde rien : %r" % (rec,))
    roles = {e["role"] for e in susp["test_temoin_nu_live.py"]}
    assert "premisse-zero" in roles, roles

    (tmp_path / "test_temoin_nu_live.py").unlink()
    (tmp_path / "test_temoin_neutre_live.py").write_text(neutre, encoding="utf-8")
    susp2 = P._suspects(P.recenser(tmp_path))
    assert "test_temoin_neutre_live.py" not in susp2, (
        "le recenseur classe suspect un montage DEJA neutralise -- il rendrait tout suspect, "
        "donc rien : %r" % (susp2,))


def test_la_liste_attestee_ne_pourrit_pas():
    """Chaque chemin atteste EXISTE. Une liste qui garde des fantomes se relit comme une mesure."""
    manquants = [rel for rel in tuple(_ATTESTES) + _FAUX_POSITIFS_MESURES
                 if not (P._TESTS / rel).exists()]
    assert not manquants, (
        "chemins attestes DISPARUS (renommes ? supprimes ?) -- regenerer le bloc par "
        "`python scripts/python/probe_933_premisses_regime.py --attester` : %r" % (manquants,))


def test_les_deux_listes_sont_DISJOINTES():
    """`--attester` imprime TOUS les suspects, faux positifs mesures COMPRIS : une regeneration
    mecanique les remettrait dans `_ATTESTES`, ou ils perdraient leur mesure et redeviendraient de
    la dette muette. Le doublon doit donc ROUGIR, pas passer."""
    double = sorted(set(_ATTESTES) & set(_FAUX_POSITIFS_MESURES))
    assert not double, (
        "chemin(s) dans les DEUX listes : %r. `--attester` ne connait pas `_FAUX_POSITIFS_MESURES` "
        "-- apres une regeneration, RETIRER de `_ATTESTES` les chemins qui y figurent deja avec "
        "leur mesure." % (double,))


def test_les_deux_listes_sont_ENCORE_ACCUSEES_par_le_recenseur():
    """LE CRAN QUI EMPECHE UNE LISTE DE MASQUER (#10027).

    Une entree qui n'est PLUS suspecte ne protege plus rien -- elle MASQUE : le jour ou le fichier
    reperd son montage, il revient dans `suspects` et la liste l'absorbe en silence. C'est
    exactement ce qui serait arrive aux 8 chemins sortis par la lecture du montage IMPORTE si on
    les y avait laisses << au cas ou >>.

    Le remede n'est PAS de retirer le cran : c'est de retirer l'ENTREE. Un fichier qui a cesse
    d'etre suspect est un fichier REPARE, et sa place est dans `test_la_liste_attestee_ne_couvre_
    pas_ce_qui_a_ete_repare`, pas dans une allowlist."""
    courants = _suspects_courants()
    assert courants, "le recenseur ne rend AUCUN suspect : il ne mesure plus rien"
    inutiles = sorted((set(_ATTESTES) | set(_FAUX_POSITIFS_MESURES)) - courants)
    assert not inutiles, (
        "%d entree(s) de liste ne sont PLUS accusees par le recenseur : %s\n"
        "Elles ne protegent plus rien et MASQUENT une regression future. Les RETIRER (et, si "
        "elles ont ete reparees, les inscrire dans le tuple `repares` du test voisin)."
        % (len(inutiles), inutiles))


def test_aucun_NOUVEAU_fichier_a_premisse_de_regime_non_declaree():
    """LE CLIQUET. La liste des fichiers a premisse de regime non neutralisee ne GRANDIT pas.

    Ce gisement est le seul que notre propre cadence alimente : chaque test live neuf qui ecrit
    `assert <stat de crit/block> == 0` sans poser son levier le rouvre, et il ne rougira que le
    jour ou quelqu'un rebasculera un defaut de harnais -- des mois plus tard, en accusant le port.
    """
    nouveaux = sorted(_suspects_courants() - set(_ATTESTES) - set(_FAUX_POSITIFS_MESURES))
    assert not nouveaux, (
        "PREMISSE DE REGIME NON DECLAREE dans %d fichier(s) : %s\n"
        "Ces fichiers LISENT une stat a zero ouvert (%s) et COMPARENT a 0 / a un positif, sans "
        "neutraliser la base au montage. Depuis la bascule #419-r5/-r6 (items Best-In-Slot par "
        "defaut), cette base n'est plus nulle : la comparaison est soit ROUGE, soit -- pire -- "
        "VERTE en ne mesurant plus rien.\n"
        "REMEDE (dans le MONTAGE, jamais dans l'assertion) : `--unit-stat <unite>:<Stat>=0`, ou "
        "les DEUX faces de `--crit`/`--crit-target` (resp. `--block-player`/`--block-target`). "
        "PAS `TACTICUS_BIS_ITEMS=0`, qui deshabille tout le roster.\n"
        "Si la premisse tient VRAIMENT sans levier, MESURE-le "
        "(`probe_933_premisses_regime.py --unites <VisualId>`) puis inscris le fichier au bloc "
        "genere via `--attester`."
        % (len(nouveaux), nouveaux, ", ".join(P._STATS_ZERO_OUVERT)))


def test_la_liste_attestee_ne_couvre_pas_ce_qui_a_ete_repare():
    """Un fichier REPARE par #933 doit avoir QUITTE la liste -- sinon le cliquet ne le garde plus.

    C'est ce qui transforme l'allowlist en cliquet : perdre le montage d'un fichier repare le fait
    revenir dans `nouveaux`, donc ROUGIR. Si l'un d'eux etait reste atteste, sa regression
    passerait inapercue.
    """
    repares = (
        "engine/runner/test_lion_helm_block_aura_live.py",     # ROUGE : `seed[az] == (0, 0)`
        "engine/runner/test_savage_echoes_live.py",            # garde `if cc == 0:` MORTE
        "engine/runner/test_executioner_live.py",              # skip `cc != 0` SYSTEMATIQUE
        "engine/runner/test_harvester_live.py",                # skip `cc != 0` SYSTEMATIQUE
        "engine/runner/test_brazier_of_holy_fire_live.py",     # skip « coup non propre »
        "engine/runner/test_sentinel_directives_live.py",      # skip « coup non propre »
        "engine/runner/test_heavy_grav_cannon_live.py",        # PREVENTIF (ecart non mesure)
        "engine/runner/test_damage_block_live.py",             # premisse en PROSE perimee
        # --- #10027 : leur montage etait DEJA la, dans le module qu'ils IMPORTENT. Le recenseur
        # ne lisait que la source du test ; il la lit desormais aussi dans le probe de montage.
        # Les inscrire ici est ce qui empeche qu'une regeneration mecanique de `_ATTESTES` les y
        # remette -- auquel cas perdre leur `--unit-stat` ne rougirait PLUS.
        "engine/runner/test_499_storm_of_wrath_live.py",       # probe_499_storm_of_wrath
        "engine/runner/test_566_vexilla_magnifica_live.py",    # probe_566_vexilla_magnifica[_decision]
        "engine/runner/test_920_maw_claws_of_thyrax_live.py",  # probe_920_maw_claws_of_thyrax_live
        "engine/runner/test_922_intoxicating_elixir_crit_live.py",  # probe_922_intoxicating_elixir_live
        "engine/runner/test_928_legacy_of_combat_live.py",     # probe_928_legacy_of_combat
        "engine/runner/test_additional_hits_roll_order_live.py",    # probe_r6b_additional_hits_order
        "engine/test_345_shield_prediction_formula_live.py",   # probe_345_shield_prediction_formula
        "engine/test_419r6r1_face_decision_live.py",           # probe_419r6r1_face_decision
    )
    restes = [rel for rel in repares if rel in _ATTESTES]
    assert not restes, (
        "fichier(s) REPARE(S) encore attestes -- le cliquet ne verrait pas la perte de leur "
        "montage : %r" % (restes,))
    for rel in repares:
        assert (P._TESTS / rel).exists(), rel
