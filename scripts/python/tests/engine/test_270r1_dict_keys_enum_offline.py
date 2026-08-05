"""#270-r1 volet 1 -- GARDE : les cles des cinq dicts a enum UNIQUE sont des MEMBRES d'enum,
et la conversion n'a rien deplace.

CE QUE CETTE GARDE TIENT, ET POURQUOI ELLE A DEUX ETAGES.

La regle « un ENTIER qui DESIGNE quelque chose passe par un ENUM » (CLAUDE.md) a fait convertir
169 cles entieres nues en membres d'`ActiveAbilityType` / `EffectType`. Une conversion de masse a
UN mode d'echec propre : ecrire le BON nom en face de la MAUVAISE valeur. `1004` devenu
`ActiveAbilityType.MultiThreatEliminator` (= 1006) ne casse aucun import et ne leve rien -- il
deplace silencieusement une entree d'une ability sur une autre. Rien dans le code ne le rattrape :
tous les consommateurs font `.get(int(...))`, donc un id devenu absent se degrade en `None`,
exactement la degradation SILENCIEUSE que ces tables existent pour eviter.

  * ETAGE 1 (`test_cles_sont_des_membres_d_enum`) -- CLIQUET PERMANENT. Chaque cle est une instance
    de l'enum attendu. Il ne se perime jamais, et c'est lui qui empeche la REOUVERTURE du gisement :
    une entree ajoutee plus tard avec un ordinal nu le fait rougir.
  * ETAGE 2 (`test_snapshot_ordinal_valeur_et_ordre`) -- ANTI-DEPLACEMENT. Les 169 couples
    (ordinal, valeur) mesures AVANT la conversion sont toujours la, avec la MEME valeur et dans le
    MEME ORDRE RELATIF. L'assertion est un SUR-ENSEMBLE ordonne, pas une egalite : une ability
    AJOUTEE au registre passe sans toucher a ce fichier (une garde qui obligerait a re-figer 169
    couples a chaque port serait contournee, pas maintenue), mais une cle DEPLACEE, PERDUE ou
    RE-VALORISEE rougit.

Le lookup par `int` brut est atteste explicitement (`test_lookup_par_int_brut`) : c'est la propriete
qui rend la conversion transparente pour les appelants, et elle tient a un detail du MRO --
`IntEnum` herite `__hash__` d'`int`, donc `d[1004]` et `d[ActiveAbilityType.MortisRound]` sont la
MEME entree. Si elle tombait (changement de version de Python, passage a un `Enum` nu), tous les
`.get(int(...))` du port rendraient `None` en silence.

100 % OFFLINE : aucun runner, aucune session Frida, aucune lecture de gameconfig.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.runner.abilities import targeting as T  # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE  # noqa: E402
from engine.runner.operations.effects import _DEFAULT_ROUNDS  # noqa: E402
from engine.services.ability_range import DYNAMIC_TARGET_GATE_BY_ABILITY  # noqa: E402
from engine.services.movement_query import SPECIAL_MOVEMENT_PATHFINDER_TYPES  # noqa: E402

# --- SNAPSHOT mesure sur `origin/master` AVANT la conversion (169 couples). ----------------------
# GENERE depuis les dicts eux-memes, jamais recopie a la main. Chaque couple = (ordinal natif,
# valeur normalisee par `_valeur_comparable`). Les `TargetingOptions` y sont aplaties en tuple de
# leurs champs SCALAIRES -- on fige la valeur EFFECTIVE, pas l'identite de l'objet, qui ne survit
# pas a un import.

SNAP_ATTACK_TYPE = (
    (1013, 0), (1004, 0), (1006, 0), (1008, 0),
    (1014, 0), (1020, 0), (1022, 0), (1025, 0),
    (1029, 0), (1042, 0), (1043, 0), (1017, 0),
    (1026, 0), (1051, 0), (1062, 0), (1065, 0),
    (1066, 0), (1067, 0), (1232, 0), (1078, 0),
    (1089, 0), (1092, 0), (1098, 0), (1104, 0),
    (1105, 0), (1113, 0), (1122, 0), (1131, 0),
    (1137, 0), (1139, 0), (1147, 0), (1148, 0),
    (1150, 0), (1160, 0), (1161, 0), (1168, 0),
    (1169, 0), (1180, 0), (1199, 0), (1200, 0),
    (1201, 0), (1202, 0), (1213, 0), (1221, 0),
    (1230, 0), (1103, 0), (1171, 0), (1059, 0),
    (1036, 0), (1154, 0), (1041, 0), (1090, 0),
    (1097, 0), (1153, 0), (1035, 0), (1003, 1),
    (1007, 1), (1016, 1), (1021, 1), (1040, 1),
    (1076, 1), (28, 2), (1119, 2), (1117, 2),
    (1186, 2), (1000, 2), (1002, 2), (1009, 2),
    (1011, 2), (1023, 2), (1018, 2), (1028, 2),
    (1037, 2), (1045, 2), (1047, 2), (1058, 2),
    (1096, 2), (1112, 2), (1118, 2), (1142, 2),
    (1143, 2), (1145, 2), (1151, 2), (1159, 2),
    (1158, 2), (1163, 2), (1166, 2), (1179, 2),
    (1115, 2), (1187, 2), (1188, 2), (1206, 2),
    (1207, 2), (1214, 2), (1219, 2), (1226, 2),
    (1102, 2), (1184, 2), (1100, 2), (1077, 2),
    (1081, 2), (1082, 2), (1140, 2), (1189, 2),
    (1116, 2),
)

SNAP_DYNAMIC_GATE = (
    (1177, 'free_adjacent_in_config_range'), (1153, 'free_adjacent_in_config_range'), (1058, 'not_derivable'),
    (1087, 'not_derivable'), (1112, 'not_derivable'), (1158, 'not_derivable'),
    (1163, 'not_derivable'), (1180, 'not_derivable'), (1202, 'not_derivable'),
    (1204, 'not_derivable'), (1011, 'valid_on_empty_tile'), (1025, 'valid_on_empty_tile'),
    (1145, 'valid_on_empty_tile'), (1168, 'valid_on_empty_tile'), (1200, 'valid_on_empty_tile'),
    (1201, 'valid_on_empty_tile'), (1213, 'valid_on_empty_tile'), (28, 'not_read'),
    (1005, 'not_read'), (1016, 'not_read'), (1038, 'not_read'),
    (1059, 'not_read'), (1081, 'not_read'), (1082, 'not_read'),
    (1101, 'not_read'), (1116, 'not_read'), (1117, 'not_read'),
    (1119, 'not_read'), (1151, 'not_read'), (1164, 'not_read'),
    (1175, 'not_read'), (1179, 'not_read'), (1197, 'not_read'),
)

SNAP_NORMAL_ATTACK_OPTS = (
    (17, (16384, False, 3, False, False, None, False, 2)),
    (1030, (16384, False, 3, False, False, None, False, 2)),
    (1114, (16384, False, 3, False, False, None, False, 2)),
    (69, (16386, False, 3, False, False, None, False, 2)),
    (1046, (16386, False, 3, False, False, None, False, 2)),
    (1086, (16386, False, 3, False, False, None, False, 2)),
    (1120, (16386, False, 3, False, False, None, False, 2)),
    (1123, (16386, False, 3, False, False, None, False, 2)),
    (1128, (16386, False, 3, False, False, None, False, 2)),
    (1138, (16386, False, 3, False, False, None, False, 2)),
    (1162, (16386, False, 3, False, False, None, False, 2)),
    (1178, (16386, False, 3, False, False, None, False, 2)),
    (1182, (16386, False, 3, False, False, None, False, 2)),
    (1205, (16386, False, 3, False, False, None, False, 2)),
    (1220, (16386, False, 3, False, False, None, False, 2)),
    (1076, (16386, False, 3, False, False, None, False, 2)),
    (1126, (16384, False, 3, False, False, None, False, 1)),
    (1146, (16384, False, 0, False, False, 1, False, 2)),
)

SNAP_DEFAULT_ROUNDS = (
    (79, 3), (1065, 1), (1162, 1), (5, 2),
    (17, 2), (18, 2), (58, 2), (1244, 2),
    (1476, 2),
)

SNAP_SPECIAL_MOVEMENT = (
    (1035, (6, 7)),
    (1140, (8, 9)),
    (1238, (10, 11)),
    (1573, (12, 13)),
)


#: Le porteur qui traverse `normal_attack_zone_contains`. Il lui faut un `visual_id` dont l'arme
#: est resoluble (sinon `None` : l'appel ne mesurerait RIEN), et il doit etre a DISTANCE -- mesure
#: du 2026-08-05 : sur un caster de MELEE (`custoBladeChampion`) les 18 profils rendent tous
#: `[True, False, False]`, donc l'appel n'aurait rien distingue. Sur `tauMarksman` (arme Range=3)
#: `1146 FloatingDeath_NormalAttack` se separe des 17 autres -- son `RANGE_ADJACENT`
#: (`overrideRange = 1`) GAGNE sur la portee d'arme. Meme porteur que
#: `test_433_r4_r2_r1_r2_ability_range_offline`.
RANGED_VISUAL_ID = "tauMarksman"

#: (dict vivant, snapshot, enum attendu, nom lisible) -- le perimetre EXACT du volet 1.
CIBLES = (
    (ABILITY_ATTACK_TYPE, SNAP_ATTACK_TYPE, ActiveAbilityType,
     "runner/abilities/attack_type.ABILITY_ATTACK_TYPE"),
    (DYNAMIC_TARGET_GATE_BY_ABILITY, SNAP_DYNAMIC_GATE, ActiveAbilityType,
     "services/ability_range.DYNAMIC_TARGET_GATE_BY_ABILITY"),
    (T.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE, SNAP_NORMAL_ATTACK_OPTS, ActiveAbilityType,
     "runner/abilities/targeting.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE"),
    (_DEFAULT_ROUNDS, SNAP_DEFAULT_ROUNDS, EffectType,
     "runner/operations/effects._DEFAULT_ROUNDS"),
    (SPECIAL_MOVEMENT_PATHFINDER_TYPES, SNAP_SPECIAL_MOVEMENT, EffectType,
     "services/movement_query.SPECIAL_MOVEMENT_PATHFINDER_TYPES"),
)


def _valeur_comparable(v):
    """Normalise une valeur pour la confronter au snapshot.

    Les `TargetingOptions` sont aplaties en tuple de leurs champs scalaires (`rules`, `self_cast`,
    les cinq champs de `range`, `force_melee_target`) : c'est la valeur EFFECTIVE que le port lit,
    et elle survit a un import -- contrairement a l'identite de l'objet preset."""
    if isinstance(v, T.TargetingOptions):
        r = v.range
        return (int(v.rules), bool(v.self_cast), int(r.only_adjacent),
                bool(r.use_range_from_config), bool(r.use_whole_board),
                r.override_range, bool(r.override_range_func), int(v.force_melee_target))
    if isinstance(v, tuple):
        return tuple(int(x) for x in v)
    if isinstance(v, str):
        return v
    return int(v)


def test_cles_sont_des_membres_d_enum():
    """ETAGE 1 -- CLIQUET : aucune cle ordinale nue ne subsiste, et aucune ne peut revenir.

    ROUGE si une entree est ajoutee plus tard avec un ordinal (`1234: ...` au lieu de
    `ActiveAbilityType.X: ...`) -- ce serait la reouverture du gisement #270-r1.
    """
    fautives = {}
    for vivant, _snap, enum_attendu, nom in CIBLES:
        hors = [k for k in vivant if not isinstance(k, enum_attendu)]
        if hors:
            fautives[nom] = [(repr(k), type(k).__name__) for k in hors]
    assert fautives == {}, (
        "ces cles ne sont pas des membres de leur enum -- un ordinal nu devient FAUX au "
        "changement de build, en silence (regle CLAUDE.md) : %r" % fautives)


def test_snapshot_ordinal_valeur_et_ordre():
    """ETAGE 2 -- ANTI-DEPLACEMENT : chaque couple mesure avant la conversion est toujours la.

    Sur-ensemble ORDONNE : une entree ajoutee passe ; une entree deplacee, perdue ou re-valorisee
    rougit. C'est ce test qui attrape « le bon nom en face de la mauvaise valeur ».
    """
    ecarts = {}
    for vivant, snap, _enum, nom in CIBLES:
        actuel = {int(k): _valeur_comparable(v) for k, v in vivant.items()}
        attendu = dict(snap)
        manquants = {o: v for o, v in attendu.items() if o not in actuel}
        revalorises = {o: (v, actuel[o]) for o, v in attendu.items()
                       if o in actuel and actuel[o] != v}
        # ordre RELATIF : la sous-suite des ordinaux connus doit etre celle du snapshot
        connus = [int(k) for k in vivant if int(k) in attendu]
        ordre_ok = connus == [o for o, _ in snap]
        if manquants or revalorises or not ordre_ok:
            ecarts[nom] = {"ordinaux_disparus": manquants, "valeur_changee": revalorises,
                           "ordre_preserve": ordre_ok}
    assert ecarts == {}, (
        "la conversion en membres d'enum n'est PAS value-preserving : %r" % ecarts)


def test_cardinalites_du_volet():
    """Le compte du volet 1 : 105 + 33 + 18 + 9 + 4 = 169 cles converties.

    `>=` cote vivant et non `==` : le volet garde ce qu'il a converti, il ne fige pas la croissance
    des tables.
    """
    tailles = [len(s) for _v, s, _e, _n in CIBLES]
    assert tailles == [105, 33, 18, 9, 4], "le snapshot du volet 1 a change de forme : %r" % tailles
    assert sum(tailles) == 169
    for vivant, snap, _enum, nom in CIBLES:
        assert len(vivant) >= len(snap), (
            "%s a PERDU des entrees : %d vivantes pour %d au snapshot"
            % (nom, len(vivant), len(snap)))


def test_lookup_par_int_brut():
    """La propriete qui rend la conversion transparente pour les appelants.

    Tous les consommateurs interrogent ces tables avec un `int` brut (`.get(int(ability_type))`).
    `IntEnum` herite `__hash__` d'`int` (MRO : `IntEnum` -> `int` -> `ReprEnum` -> `Enum`), donc la
    cle `ActiveAbilityType.MortisRound` et l'entier `1004` designent la MEME entree. On l'atteste
    sur les 169 couples plutot que de le supposer.
    """
    for vivant, snap, _enum, nom in CIBLES:
        for ordinal, valeur in snap:
            assert ordinal in vivant, "%s : `%d in dict` est faux apres conversion" % (nom, ordinal)
            assert _valeur_comparable(vivant[ordinal]) == valeur, (
                "%s : le lookup par int brut %d ne rend pas la valeur attendue" % (nom, ordinal))


def test_generalisation_les_accesseurs_publics_sur_les_169():
    """GENERALISATION -- la conversion traversee par le chemin REEL des appelants.

    POURQUOI CET ETAGE EXISTE. Les tests de comportement qui consomment ces cinq tables n'en
    exercent qu'une POIGNEE : le registre des abilities porte plus de cent entrees, et les tests
    live en montent quelques-unes. Un mode d'echec qui ne frapperait qu'une cle jamais jouee ne
    serait vu par personne. Ici on balaye les 169, mais par les ACCESSEURS PUBLICS (jamais par le
    dict), donc a travers le `.get(int(...))` que font reellement les consommateurs.

    LA PROPRIETE ASSERTIONNEE est celle qui rend la conversion sans effet de bord : pour chaque
    cle, interroger l'accesseur avec l'ORDINAL NU et avec le MEMBRE D'ENUM rend la MEME chose.
    C'est plus fort qu'une egalite au snapshot -- elle vaut meme pour les entrees ajoutees apres
    ce volet, et elle ne se perime pas.

    Et elle DISCRIMINE : `ability_has_attack_type` est aussi confronte aux deux autres valeurs
    d'`AbilityAttackType`, qui doivent rendre `False`. Sans ce controle, un accesseur qui rendrait
    `True` pour tout passerait les deux formes de l'appel.
    """
    from engine.runner.abilities import attack_type as AT  # noqa: E402
    from engine.runner.operations import effects as OPE  # noqa: E402
    from engine.services import ability_range as AR  # noqa: E402
    from engine.services import movement_query as MQ  # noqa: E402

    # 105 -- `attack_type.ability_has_attack_type` (le predicat `AActiveAbility$$HasAttackType`)
    for ordinal, attendu in SNAP_ATTACK_TYPE:
        membre = ActiveAbilityType(ordinal)
        assert AT.ability_has_attack_type(ordinal, attendu) is True
        assert AT.ability_has_attack_type(membre, attendu) is True
        for autre in ({0, 1, 2} - {attendu}):
            assert AT.ability_has_attack_type(ordinal, autre) is False, (
                "%d : le predicat ne discrimine pas AbilityAttackType" % ordinal)

    # 33 -- `ability_range.dynamic_target_gate_of` (regime de `GetDynamicInvalidTargetReason`)
    for ordinal, attendu in SNAP_DYNAMIC_GATE:
        membre = ActiveAbilityType(ordinal)
        assert AR.dynamic_target_gate_of(ordinal) == attendu
        assert AR.dynamic_target_gate_of(membre) == attendu

    # 9 -- `effects.default_amount_of_rounds` (`StaticBattleRules.Effect$$DefaultAmountOfRounds`)
    for ordinal, attendu in SNAP_DEFAULT_ROUNDS:
        membre = EffectType(ordinal)
        assert OPE.default_amount_of_rounds(ordinal) == attendu
        assert OPE.default_amount_of_rounds(membre) == attendu

    # 4 -- `movement_query.get_pathfinder_type_for_unit` (`MovementQuery$$GetPathfinderTypeForUnit`)
    #      Le porteur de l'effet est simule par le canal `has_effect`, exactement comme le font les
    #      deux consommateurs reels (`state.effects.has_effect` / `ctx.has_effect`).
    for ordinal, (walk, fly) in SNAP_SPECIAL_MOVEMENT:
        membre = EffectType(ordinal)
        for sonde in (ordinal, membre):
            porte = (lambda et, _s=sonde: int(et) == int(_s))
            assert MQ.get_pathfinder_type_for_unit(porte, ()) == walk
            assert MQ.get_pathfinder_type_for_unit(porte, ("Flying",)) == fly
            assert MQ.get_pathfinder_type_for_unit(porte, (), True) == 0, (
                "%d : `ignoreSpecialMovement` doit court-circuiter la table" % ordinal)

    # 18 -- `ability_range.normal_attack_zone_contains`, seul appelant SANS ETAT de la table des
    #      options d'attaque normale. On compare les DEUX formes de l'appel sur quatre distances :
    #      la reponse depend du profil retrouve dans la table, donc une cle deplacee change la zone.
    zones = {}
    for ordinal, _profil in SNAP_NORMAL_ATTACK_OPTS:
        membre = ActiveAbilityType(ordinal)
        reponses = []
        for d in (1, 2, 3, 4):
            par_int = AR.normal_attack_zone_contains(ordinal, RANGED_VISUAL_ID, d)
            par_membre = AR.normal_attack_zone_contains(membre, RANGED_VISUAL_ID, d)
            assert par_int == par_membre, (
                "%d : la zone d'attaque normale differe selon la forme de la cle (d=%d)"
                % (ordinal, d))
            reponses.append(par_int)
        # ANTI-DEGENERESCENCE : un `None` partout ferait passer l'egalite sans rien mesurer.
        assert any(r is not None for r in reponses), (
            "%d : la zone est indeterminee aux quatre distances -- l'appel ne mesure RIEN, "
            "corriger le porteur (%s) plutot que d'accepter le vert" % (ordinal, RANGED_VISUAL_ID))
        zones[ordinal] = tuple(reponses)
    # ET l'appel DISCRIMINE : si les 18 profils rendaient la meme zone, l'egalite ci-dessus
    # tiendrait meme avec la table entierement melangee. Mesure : `1146` se separe des 17 autres.
    assert len(set(zones.values())) > 1, (
        "les 18 profils rendent tous la meme zone sur %s -- l'appel ne distingue rien, donc "
        "l'egalite int/membre ne prouve rien : %r" % (RANGED_VISUAL_ID, zones))
