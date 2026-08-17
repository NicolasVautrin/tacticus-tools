"""#270-r4 -- GARDE : les litteraux entiers des TROIS ROLES JAMAIS TRIES sont des membres d'enum.

CE QUE CETTE TRANCHE A TRIE, ET CE QUI LA DISTINGUE DES QUATRE PRECEDENTES.

Les volets 1 et 2 portaient sur des CLES DE DICT, #270-r1-r1 sur des ELEMENTS DE CONTENEUR,
#270-r1-r1-r3 sur les ROLES DERIVES (affectation / valeur de retour / indice). Restaient les trois
GROS roles que le tri site-par-site n'avait JAMAIS visites -- `argument d'appel` (189),
`expression` (103), `comparaison` (49), soit **341 positions**. Aucun discriminant structurel n'y
existe : ni couverture de groupe (il n'y a pas de groupe), ni voisin qui contraigne. Le seul
discriminant est, SITE PAR SITE, le NOM deja ecrit au site ou le TYPE DECLARE lu dans
`data/symbols/<build>/frida/methods.tsv`.

RESULTAT DU TRI : **62 litteraux convertis** (75 membres ecrits -- six sites de `status.py`
derivent l'id ET le nom du meme membre), **279 restent des SCALAIRES**, et c'est un RESULTAT.
La doctrine annoncait ces trois roles « majoritairement des timeouts RPC et des pourcentages » :
c'est verifie, `100` a lui seul y occupe 100 positions.

TROIS ATTRIBUTIONS REPOSENT SUR UNE SIGNATURE LUE, PAS SUR UN NOM :
  * `IdunBattle.Entities.Enum.EffectTargetType` -- type du dernier parametre de
    `IdunBattleLogic.Entities.DSLTriggers.HasEffect` (et de ses quatre voisins). MIRROR NEUF de la
    tranche ; `6` y vaut `Both`, alors que `6` est aussi `EffectType.PoisonGrenade`.
  * `IdunBattle.Streams.TagKey` -- type du parametre `tag` d'
    `IdunBattleLogic.Entities.DSLBehaviors.Inform`. Le port nommait ce champ `message_type` : le
    NOM du port etait FAUX, le type declare le corrige.
  * `IdunBattle.Streams.GroupType` -- type du parametre `groupType` d'
    `IdunBattleLogic.Entities.DSLBehaviors.Group`.
  * `IdunBattleLogic.Utils.Hex.Corner` -- type du parametre `direction` d'
    `IdunBattle.Core.Services.BattleQuery.GetTilesInTriangleShape`. Le build porte CINQ autres
    enums nommes `Corner` (Unity/SimpleUI) : le nom court aurait apparie faux.

UNE FAUSSE ATTRIBUTION EVITEE, ET ELLE AURAIT ETE SILENCIEUSE. `entities/triggers.py` comparait
`ctx.attack_ability_type == 1013`, et `1013` EST un membre valide d'`ActiveAbilityType`
(`PrecisionShot_Attack`). L'y convertir aurait « resolu » sans rien casser -- et aurait ecrit le
mauvais concept : le decompile nomme ce littéral `AbilityOrEffect 0x3f5`, argument du
`DirectAbilitySelector` de la 2e branche d'`IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`,
c'est-a-dire un marqueur de KIND. Le build ne publie aucun enum `AbilityOrEffect` ; le foyer nomme
du depot est `runner/abilities/attack_type.NORMAL_ATTACK_KIND`. L'etage 6 mesure que la confusion
aurait ete muette.

SIX ETAGES.

  * ETAGE 1 -- RENUMEROTAGE : chaque membre ecrit vaut TOUJOURS l'ordinal mesure a la conversion.
    C'est le cran qui manque a `probe_313`, qui compare le MIRROR au BUILD et redevient VERT des
    qu'on regenere le mirror -- alors que la valeur ECRITE AU SITE, elle, a change.
  * ETAGE 2 -- CLIQUET DE FORME : chaque fichier porte toujours au moins les occurrences que la
    tranche y a mises. ⚠ Il RESOUT LES ALIAS D'IMPORT (`StatPart as _SP`) : le cliquet de
    #270-r1-r1-r3 ne les voyait pas, donc un site alias lui etait invisible -- meme forme de trou
    que celui du recenseur, un cran plus bas.
  * ETAGE 3 -- ACCESSEURS PUBLICS : les chemins REELS des appelants, avec l'ordinal ET avec le
    membre, et avec anti-degenerescence (les reponses doivent DISCRIMINER).
  * ETAGE 4 -- LE REGISTRE : `EffectTargetType` est inscrit au registre de `probe_313`, SOUS GARDE,
    apparie par son nom PLEIN. Ce gisement s'est rouvert CINQ fois par notre propre cadence.
  * ETAGE 5 -- LA GARDE DEPORTEE de `services/static_battle_rules.py` : ce module ne PEUT PAS
    importer `EffectType` (cycle MESURE, cf. l'encadre #270-r1-r1 en tete de ce module), donc son
    `et == 0x3a` reste en littéral. Le test, lui, importe les deux couches et confronte la valeur.
  * ETAGE 6 -- NON-DEGENERESCENCE de l'attribution `1013` : la confusion evitee ci-dessus aurait
    ete SILENCIEUSE. Le test l'ecrit, et ASSERTIONNE SON PROPRE NON-VIDE -- un controle qui rend
    un ensemble vide passerait pour vert (lecon de #270-r1-r1-r3, etage 5).

CE QUI RESTE DELIBEREMENT EN LITTERAL, et c'est un RESULTAT, pas un oubli -- le dernier bloc du
fichier le rend EXECUTABLE : les `100` de pourcentage (100 positions a eux seuls), les timeouts
RPC (40/60/90), les sentinelles de distance (`99`, `0x7FFFFFFF`), la graine et l'etat du Mersenne
Twister, les SLOTS DE VTABLE (`slot == 4`), les comptes de pieds (`feet_count == 7`), les VALEURS
par defaut de constante gameconfig, et la BORNE `direction > 5` de `battle_query` -- qui borne
l'enum `Corner` sans designer `SouthEast`. Liste raisonnee : `docs/rl/case-270r4-trois-roles.md`.

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import ast
import importlib
import sys
from enum import Enum
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

ENGINE = PYDIR / "engine"

from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType  # noqa: E402
from engine.entities.effect_target_type import EffectTargetType  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.stats import StatPart, StatType  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.entities.unit_faction import UnitFaction  # noqa: E402
from engine.entities.unit_flag import UnitFlag  # noqa: E402
from engine.hex_corner import Corner  # noqa: E402
from engine.streams.group_type import GroupType  # noqa: E402
from engine.streams.tag_key import TagKey  # noqa: E402

ENUMS = {c.__name__: c for c in (
    ActiveAbilityType, Corner, DamageProfileType, EffectTargetType, EffectType, GroupType,
    StatPart, StatType, TagKey, TriggeredAbilityType, UnitFaction, UnitFlag, UnitTrait)}


def _resoudre(cle: str):
    cls, membre = cle.split(".", 1)
    return getattr(ENUMS[cls], membre)


# ── TABLES -- DERIVEES de l'AST (delta arbre de base -> arbre livre), jamais retranscrites.
#
# `SITES` : (fichier sous `engine/`) -> {"Enum.membre": occurrences INTRODUITES par la tranche}.
# La cle est un COMPTE, pas un numero de ligne : elle survit a un deplacement de code, et un
# compte qui BAISSE signale un retour a l'ordinal nu.
# `ORDINAUX` : l'ordinal MESURE de chaque membre au moment de la conversion -- le cran
# anti-renumerotage. Il ne se regenere pas : c'est ce qui en fait un temoin.

SITES = {
    "dsl/base.py": {
        "StatType.HEALTH": 1,
    },
    "entities/abilities/active_ability.py": {
        "Corner.NorthEast": 1,
        "Corner.SouthWest": 1,
    },
    "entities/effects/loki/hits.py": {
        "StatPart.MISSING": 1,
    },
    "entities/effects/loki/status.py": {
        "EffectType.Stunned_CantUseAbility": 2,
        "EffectType.Stunned_DamageModifier": 2,
        "EffectType.Stunned_MovementOverride": 2,
        "EffectType.Taunted_BlockMovement": 2,
        "EffectType.Taunted_CantUseAbility": 2,
        "EffectType.Taunted_RefreshUnitTurnFinished": 2,
    },
    "entities/selectors/units.py": {
        "UnitFlag.Resurrected": 1,
        "UnitTrait.Hero": 1,
    },
    "entities/stats.py": {
        "StatPart.MISSING": 2,
        "StatPart.OVERRIDE": 2,
    },
    "entities/triggers.py": {
        "EffectTargetType.Both": 4,
    },
    "playbook/noncomparable/nova_boost.py": {
        "ActiveAbilityType.NovaBoost": 1,
    },
    "playbook/noncomparable/nova_shield.py": {
        "ActiveAbilityType.NovaShield": 1,
    },
    "playbook/noncomparable/thrice_blessed_conflagration.py": {
        "ActiveAbilityType.ThriceBlessedConflagration": 1,
    },
    "playbook/prediction/abilities.py": {
        "ActiveAbilityType.HammerOfWrath": 4,
    },
    "runner/components.py": {
        # SITE MIGRE (#873, commit `ea55462c`) : il vivait dans
        # `runner/abilities/behaviours/context.py`, ecrit `_SP.MISSING` par alias. #873 a DELEGUE
        # toute la ventilation des parts a `HealthComponent.get_stat_part` -- le membre nomme a
        # suivi, en nom BRUT cette fois. Le gisement n'a PAS regresse (aucun ordinal nu n'est
        # revenu) ; c'est le TEMOIN qui pointait un fichier, et le fichier a change. `total`
        # (75), `ORDINAUX` (48) et `len(SITES)` (26) sont INCHANGES : un site deplace, pas un site
        # perdu. C'est ce cas exact que le message de l'etage 2 nomme (« site deplace hors du
        # fichier ») -- il l'a d'ailleurs attrape, et `master` en est reste ROUGE.
        "StatPart.MISSING": 1,
    },
    "runner/abilities/blacklegion.py": {
        "Corner.NorthEast": 1,
        "Corner.SouthWest": 1,
    },
    "runner/abilities/deathguard.py": {
        "GroupType.PlagueWind_Attack1": 1,
        "GroupType.PlagueWind_Attack2": 1,
        "GroupType.PlagueWind_Attack3": 1,
    },
    "runner/abilities/ultramarines.py": {
        "Corner.NorthEast": 1,
        "Corner.SouthWest": 1,
        "TagKey.Is_Charging": 1,
    },
    "runner/operations/spawn.py": {
        "EffectType.GeminaeSuperia_JustSummonedEffect": 1,
    },
    "runner/operations/triggers/loki/betrayer.py": {
        "TagKey.Is_Automatic_Activation": 1,
    },
    "runner/operations/triggers/loki/cursed_plague_bell.py": {
        "DamageProfileType.Psychic": 1,
    },
    "runner/operations/triggers/loki/fire.py": {
        "TagKey.Target_Id": 1,
    },
    "runner/operations/triggers/loki/hailstrike.py": {
        "DamageProfileType.Piercing": 1,
    },
    "runner/operations/triggers/loki/harlequins_panoply.py": {
        "TagKey.Attacker_Id": 1,
    },
    "runner/operations/triggers/loki/hateful_assault.py": {
        "DamageProfileType.Power": 1,
    },
    "runner/operations/triggers/loki/master_of_the_tutelaries.py": {
        "DamageProfileType.Psychic": 1,
    },
    "runner/operations/triggers/loki/stormboyz_strike.py": {
        "TagKey.Unit_Foot_Tile_Id_1": 1,
    },
    "services/trait_damage_limits.py": {
        "StatPart.MISSING": 1,
    },
    "utilities/tile.py": {
        "EffectType.CallRipperSwarms_PendingSummon": 1,
        "EffectType.Contaminated": 1,
        "EffectType.DespoiledGround": 1,
        "EffectType.EnvEndBombardment": 1,
        "EffectType.EnvEndBombardment_Incoming": 1,
        "EffectType.Fire": 1,
        "EffectType.FirstAidHeal": 1,
        "TriggeredAbilityType.DefenderOfTheGreaterGood": 1,
        "TriggeredAbilityType.KustomForceField": 1,
        "TriggeredAbilityType.MoltenForm": 1,
        "TriggeredAbilityType.SaviorProtocols": 2,
        "UnitFaction.Tau": 1,
        "UnitTrait.Chaos": 1,
        "UnitTrait.Hero": 1,
        "UnitTrait.Imperial": 1,
        "UnitTrait.Mechanical": 1,
        "UnitTrait.Object": 2,
        "UnitTrait.Summon": 3,
        "UnitTrait.Xenos": 1,
    },
}

ORDINAUX = {
    "ActiveAbilityType.HammerOfWrath": 1153,
    "ActiveAbilityType.NovaBoost": 1192,
    "ActiveAbilityType.NovaShield": 1194,
    "ActiveAbilityType.ThriceBlessedConflagration": 1187,
    "Corner.NorthEast": 1,
    "Corner.SouthWest": 4,
    "DamageProfileType.Piercing": 20,
    "DamageProfileType.Power": 14,
    "DamageProfileType.Psychic": 13,
    "EffectTargetType.Both": 6,
    "EffectType.CallRipperSwarms_PendingSummon": 1094,
    "EffectType.Contaminated": 1244,
    "EffectType.DespoiledGround": 1476,
    "EffectType.EnvEndBombardment": 1360,
    "EffectType.EnvEndBombardment_Incoming": 1359,
    "EffectType.Fire": 5,
    "EffectType.FirstAidHeal": 10,
    "EffectType.GeminaeSuperia_JustSummonedEffect": 1061,
    "EffectType.Stunned_CantUseAbility": 1165,
    "EffectType.Stunned_DamageModifier": 1167,
    "EffectType.Stunned_MovementOverride": 1166,
    "EffectType.Taunted_BlockMovement": 25,
    "EffectType.Taunted_CantUseAbility": 26,
    "EffectType.Taunted_RefreshUnitTurnFinished": 1237,
    "GroupType.PlagueWind_Attack1": 75,
    "GroupType.PlagueWind_Attack2": 76,
    "GroupType.PlagueWind_Attack3": 77,
    "StatPart.MISSING": 4,
    "StatPart.OVERRIDE": 7,
    "StatType.HEALTH": 5,
    "TagKey.Attacker_Id": 182,
    "TagKey.Is_Automatic_Activation": 191,
    "TagKey.Is_Charging": 192,
    "TagKey.Target_Id": 179,
    "TagKey.Unit_Foot_Tile_Id_1": 121,
    "TriggeredAbilityType.DefenderOfTheGreaterGood": 1155,
    "TriggeredAbilityType.KustomForceField": 1102,
    "TriggeredAbilityType.MoltenForm": 1221,
    "TriggeredAbilityType.SaviorProtocols": 1120,
    "UnitFaction.Tau": 9,
    "UnitFlag.Resurrected": 14,
    "UnitTrait.Chaos": 2026,
    "UnitTrait.Hero": 16,
    "UnitTrait.Imperial": 26,
    "UnitTrait.Mechanical": 5,
    "UnitTrait.Object": 13,
    "UnitTrait.Summon": 2,
    "UnitTrait.Xenos": 1006,
}


# ───────────────────────────────────────────────── ETAGE 1 : RENUMEROTAGE (le cran du dessous)

def test_etage1_aucun_membre_ecrit_n_a_change_d_ordinal():
    """Chaque membre ecrit par la tranche vaut TOUJOURS l'ordinal mesure a la conversion.

    POURQUOI CE N'EST PAS REDONDANT AVEC `probe_313`. Le probe compare le MIRROR au BUILD : si le
    jeu renumerote `TagKey.Is_Charging` de 192 a 193 et qu'on regenere le mirror, le probe REDEVIENT
    VERT -- alors que le site, lui, a silencieusement change de valeur. Ici l'ordinal est FIGE dans
    le test, donc il rougit, et il NOMME le membre coupable."""
    ecarts = []
    for cle, attendu in sorted(ORDINAUX.items()):
        try:
            v = int(_resoudre(cle))
        except (AttributeError, KeyError) as e:
            ecarts.append("%s : INTROUVABLE (%s)" % (cle, type(e).__name__))
            continue
        if v != attendu:
            ecarts.append("%s : ordinal %d, la tranche avait mesure %d" % (cle, v, attendu))
    assert not ecarts, ("RENUMEROTAGE (ou membre disparu) sur %d/%d membre(s) :\n  %s"
                        % (len(ecarts), len(ORDINAUX), "\n  ".join(ecarts)))


def test_etage1b_la_table_couvre_bien_la_tranche_livree():
    """Anti-degenerescence de l'etage 1 : une table videe le rendrait VERT sur rien.

    Les trois comptes sont ceux de la tranche livree ; ils ne se re-derivent pas ici -- c'est
    justement ce qui en fait un temoin, et pas un miroir de l'etat courant.

    75 membres ecrits pour 62 litteraux retires : les six `SubEffectSpec` de `status.py` derivent
    l'id ET le nom du MEME membre (`int(EffectType.X)` + `EffectType.X.name`), et six littéraux
    voisins de magnitude <= 3 -- hors perimetre du recenseur, mais sur les MEMES appels -- ont ete
    convertis avec eux : les laisser en ordinal nu a cote d'un membre nomme aurait rendu le site
    illisible (`_has(ctx, "unit_traits", 2) or _has(ctx, "unit_traits", UnitTrait.Object)`)."""
    total = sum(sum(m.values()) for m in SITES.values())
    assert total == 75, "la tranche a ecrit 75 membres, la table en declare %d" % total
    assert len(ORDINAUX) == 48, "48 membres distincts attendus, %d declares" % len(ORDINAUX)
    assert len(SITES) == 26, "26 fichiers attendus, %d declares" % len(SITES)


# ──────────────────────────────────────────── ETAGE 2 : CLIQUET DE FORME (le gisement se rouvre)

def _occurrences(rel: str) -> dict[str, int]:
    """Les `<Enum>.<membre>` d'un fichier, ALIAS D'IMPORT RESOLUS.

    Le cliquet de #270-r1-r1-r3 comparait `n.value.id` a la liste des noms d'enum : un site ecrit
    via un alias (`from ...stats import StatPart as _SP` puis `_SP.MISSING`) lui etait donc
    INVISIBLE, et son compte se serait tu sur un retour a l'ordinal nu. On lit les alias."""
    arbre = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    alias: dict[str, str] = {}
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                court = al.name.rsplit(".", 1)[-1]
                if court in ENUMS:
                    alias[al.asname or court] = court
    out: dict[str, int] = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            nom = alias.get(n.value.id, n.value.id if n.value.id in ENUMS else None)
            if nom is None:
                continue
            cle = "%s.%s" % (nom, n.attr)
            out[cle] = out.get(cle, 0) + 1
    return out


def test_etage2_aucun_site_n_est_revenu_a_l_ordinal_nu():
    """Chaque fichier porte TOUJOURS au moins les occurrences que la tranche y a mises.

    C'est le cliquet : ce gisement est le seul que notre PROPRE cadence alimente. Un
    `Inform(0xc0)` reecrit a la place d'`Inform(int(TagKey.Is_Charging))` fait baisser le compte."""
    manques = []
    for rel, attendus in sorted(SITES.items()):
        if not (ENGINE / rel).is_file():
            manques.append("%s : FICHIER ABSENT" % rel)
            continue
        vus = _occurrences(rel)
        for cle, n in sorted(attendus.items()):
            if vus.get(cle, 0) < n:
                manques.append("%s : %s vu %d fois, la tranche en avait mis %d"
                               % (rel, cle, vus.get(cle, 0), n))
    assert not manques, ("ORDINAL NU REVENU (ou site deplace hors du fichier) :\n  %s"
                         % "\n  ".join(manques))


def test_etage2b_le_cliquet_resout_bien_les_alias():
    """Anti-degenerescence de l'etage 2 : sans resolution d'alias il se tairait sur `context.py`.

    Un cliquet qui compare le nom BRUT rendrait 0 sur ce fichier et passerait pour vert. Le test
    mesure que la resolution mord VRAIMENT.

    ⚠ TEMOIN CHANGE (#270-r1-r1-r3-r1). Il visait `_SP.MISSING`, que #873 a fait migrer vers
    `runner/components.py` en nom BRUT -- l'anti-degenerescence tombait donc alors meme que la
    resolution d'alias marchait toujours. Le nouveau temoin est `_ST.HEALTH` du MEME fichier
    (l'import `StatType as _ST` y est toujours, et le nom brut `StatType.` n'y apparait nulle
    part), donc l'etage garde exactement le meme pouvoir : il rougit si `_occurrences` cesse de
    resoudre les alias. Le CHOIX du membre est arbitraire ; ce qui compte est qu'il soit ecrit
    par alias et seulement par alias."""
    rel = "runner/abilities/behaviours/context.py"
    assert _occurrences(rel).get("StatType.HEALTH", 0) >= 1, (
        "l'alias `StatType as _ST` de %s n'est plus resolu -- le cliquet est redevenu aveugle" % rel)
    # ... et le nom BRUT n'apparait PAS dans ce fichier : c'est ce qui prouve que seul l'alias
    # le rend visible.
    assert "StatType.HEALTH" not in (ENGINE / rel).read_text(encoding="utf-8"), (
        "le site de %s n'est plus ecrit par alias : cet etage ne mesure plus rien, le reecrire "
        "sur un autre porteur d'alias ou le supprimer" % rel)


# ──────────────────────────────────────────────────────────── ETAGE 3 : ACCESSEURS PUBLICS

def test_etage3_les_parts_de_stat_repondent_pareil_par_ordinal_et_par_membre():
    """`StatComponent` / `FillUpStatComponent` -- le chemin REEL, avec anti-degenerescence."""
    from engine.entities.stats import FillUpStatComponent, StatComponent

    c = StatComponent(initial=40)
    c.override.override = 77
    assert c.get_stat_part(int(StatPart.OVERRIDE)) == c.get_stat_part(StatPart.OVERRIDE) == 77
    assert c.get_stat_part(int(StatPart.MISSING)) == c.get_stat_part(StatPart.MISSING) == 0
    assert c.get_stat_part(StatPart.OVERRIDE) != c.get_stat_part(StatPart.MISSING)   # DISCRIMINE

    f = FillUpStatComponent(maximum=100, current=30)
    assert f.get_stat_part(int(StatPart.MISSING)) == f.get_stat_part(StatPart.MISSING) == 70
    assert f.get_stat_part(StatPart.MAXIMUM) == 100 and f.get_stat_part(StatPart.CURRENT) == 30
    assert f.get_stat_part(StatPart.MISSING) != f.get_stat_part(StatPart.MAXIMUM)    # DISCRIMINE


def test_etage3b_group_unit_stat_part_missing_rend_les_membres_MORTS():
    """`group_unit_stat_part(StatPart.MISSING, ...)` = `n - restants` (le compte des morts)."""
    from engine.services.trait_damage_limits import group_unit_stat_part

    # 4 membres, 100 PV au total, 50 PV restants -> 2 restants, donc 2 morts.
    morts = group_unit_stat_part(int(StatPart.MISSING), 100, 4, 50)
    assert morts == group_unit_stat_part(StatPart.MISSING, 100, 4, 50) == 2
    # DISCRIMINE : `Current` rend les VIVANTS, pas les morts.
    assert group_unit_stat_part(StatPart.CURRENT, 100, 4, 50) == 2
    assert group_unit_stat_part(StatPart.MISSING, 100, 4, 100) == 0     # personne de mort
    assert group_unit_stat_part(StatPart.MISSING, 100, 4, 25) == 3      # trois morts


def test_etage3c_le_defaut_degrade_de_get_stat_ne_repond_que_sur_HEALTH():
    """`dsl.base._default_get_stat` -- le membre ET l'ordinal, avec anti-degenerescence."""
    from engine.dsl.base import _default_get_stat

    u = {"hp": 42}
    assert _default_get_stat(u, int(StatType.HEALTH), 0, 1) == 42
    assert _default_get_stat(u, StatType.HEALTH, 0, 1) == 42
    # DISCRIMINE : tout autre StatType rend 0 (le defaut degrade ne lit que la PV).
    assert _default_get_stat(u, StatType.CRIT_CHANCE, 0, 1) == 0
    assert _default_get_stat(u, StatType.ARMOR, 0, 1) == 0


def test_etage3d_les_feuilles_de_tile_gatent_bien_sur_leurs_membres():
    """`utilities/tile.py` -- 19 membres convertis ; on traverse les trois formes de gate.

    Le gate est `ctx`/`meta` : la feuille rend 0 quand le membre attendu n'est PAS present, et sa
    valeur de poids quand il l'est. Sans le volet « ces reponses DISCRIMINENT », l'egalite
    tiendrait aussi sur une feuille qui rendrait toujours la meme chose."""
    from engine.utilities.tile import (ContaminatedUtility, DespoiledGroundUtility,
                                       SaviorProtocolsUtility)
    from engine.weights import Weights

    wt = Weights({"Default": {
        "Contaminated": {"AffectedUnit": -25},
        "DespoiledGround": {"ChaosAffectedUnit": -5, "ImperialAndXenosAffectedUnit": -25},
        "SaviorProtocols": {"PerUnitWithAbilityInRange": 20},
    }})
    ct = ContaminatedUtility()
    meta_ok = {"tile_effect_type_ids": [int(EffectType.Contaminated)]}
    meta_ko = {"tile_effect_type_ids": [int(EffectType.Fire)]}
    assert ct.evaluate(None, meta_ok, {}, wt) != 0.0
    assert ct.evaluate(None, meta_ko, {}, wt) == 0.0          # DISCRIMINE

    dg = DespoiledGroundUtility()
    meta_dg = {"tile_effect_type_ids": [int(EffectType.DespoiledGround)]}
    assert dg.evaluate(None, meta_dg, {"unit_traits": [int(UnitTrait.Chaos)]}, wt) != 0.0
    assert dg.evaluate(None, meta_dg, {"unit_traits": [int(UnitTrait.Imperial)]}, wt) != 0.0
    assert dg.evaluate(None, meta_dg, {"unit_traits": [int(UnitTrait.Xenos)]}, wt) != 0.0
    assert dg.evaluate(None, meta_dg, {"unit_traits": [int(UnitTrait.Hero)]}, wt) == 0.0  # DISCRIMINE

    sp = SaviorProtocolsUtility()
    ab = int(TriggeredAbilityType.SaviorProtocols)
    meta_sp = {"ability_friend_counts": {ab: 2}}
    assert sp.evaluate(None, meta_sp, {"unit_faction": int(UnitFaction.Tau)}, wt) != 0.0
    # DISCRIMINE sur la FACTION (le gate natif est `faction == Tau`) ...
    assert sp.evaluate(None, meta_sp, {"unit_faction": int(UnitFaction.Necrons)}, wt) == 0.0
    # ... et sur le PORTEUR (l'unite qui a deja l'ability est exclue).
    assert sp.evaluate(None, meta_sp,
                       {"unit_faction": int(UnitFaction.Tau),
                        "unit_triggered_abilities": [ab]}, wt) == 0.0


def test_etage3e_les_sous_effets_de_statut_portent_id_ET_nom_du_meme_membre():
    """`status.py` -- la conversion y derive l'id ET le nom du MEME membre : ils ne peuvent
    plus diverger. Avant, le nom etait une CHAINE recopiee a cote d'un ordinal en dur."""
    from engine.entities.effects.loki.status import StunnedEffect, TauntedEffect

    for cls, attendus in ((StunnedEffect, (EffectType.Stunned_CantUseAbility,
                                           EffectType.Stunned_MovementOverride,
                                           EffectType.Stunned_DamageModifier)),
                          (TauntedEffect, (EffectType.Taunted_BlockMovement,
                                           EffectType.Taunted_CantUseAbility,
                                           EffectType.Taunted_RefreshUnitTurnFinished))):
        specs = cls.sub_effects_on_apply(cls.__new__(cls))
        assert len(specs) == 3, (cls.__name__, len(specs))
        for spec, membre in zip(specs, attendus):
            assert int(spec.effect_type) == int(membre), (cls.__name__, spec, membre)
            assert spec.name == membre.name, (cls.__name__, spec.name, membre.name)


# ────────────────────────────────────────────────────────────────────── ETAGE 4 : LE REGISTRE

MIRROR_NEUF = ("EffectTargetType", "engine/entities/effect_target_type.py",
               "IdunBattle.Entities.Enum.EffectTargetType")


def test_etage4_le_mirror_neuf_est_au_registre_de_probe_313():
    """Un mirror neuf hors registre en sort ORPHELIN -- cinq precedents, dont un `master` rouge."""
    import probe_313_enum_mirror_bijection as P

    cls, rel, cle = MIRROR_NEUF
    par_cls = {m.cls: m for m in P.REGISTRE}
    assert cls in par_cls, "%s n'est PAS au registre de probe_313" % cls
    m = par_cls[cls]
    assert m.rel == rel, "%s : registre dit %s, la tranche a ecrit %s" % (cls, m.rel, rel)
    assert m.cle == cle, "%s : cle %s, attendu le nom PLEIN %s" % (cls, m.cle, cle)
    assert m.garde, "%s doit etre SOUS GARDE (bijection exigee), pas en dette" % cls
    assert m.strict, "%s recopie les noms du jeu VERBATIM : strict attendu" % cls


def test_etage4b_le_mirror_neuf_est_en_bijection_avec_le_build():
    """La bijection elle-meme, rejouee ici pour que le test soit autoportant."""
    import probe_313_enum_mirror_bijection as P

    cls, _rel, cle = MIRROR_NEUF
    build = (P.REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    natif = P.enum_natif(build, cle)
    assert natif, "%s : `enums.tsv` du build %s ne porte pas la cle %s" % (cls, build, cle)
    port = {int(m): m.name for m in ENUMS[cls]}
    assert set(natif) == set(port), (
        "%s : MANQUANTS=%s MORTS=%s"
        % (cls, sorted(set(natif) - set(port)), sorted(set(port) - set(natif))))
    for v, noms in natif.items():
        assert port[v] in noms, "%s : le port dit %d=%s, le build dit %s" % (cls, v, port[v],
                                                                            sorted(noms))


def test_etage4c_le_nom_court_du_mirror_neuf_n_a_aucun_homonyme_dans_le_build():
    """`Corner` en a CINQ, `Edge` un -- et c'est ce qui impose l'appariement par nom PLEIN.

    Ici l'appariement par nom court aurait ete correct, et c'est justement l'exception : le test
    MESURE l'unicite au lieu de la supposer, pour qu'un build qui introduirait un homonyme rougisse
    au lieu de rendre l'appariement fragile en silence."""
    import probe_313_enum_mirror_bijection as P
    from symbols_layout import build_dir

    cls, _rel, cle = MIRROR_NEUF
    build = (P.REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    tsv = build_dir(build) / "frida" / "enums.tsv"
    homonymes = [ligne.split("\t", 1)[0] for ligne in tsv.read_text(encoding="utf-8").splitlines()
                 if ligne and not ligne.startswith("#")
                 and ligne.split("\t", 1)[0].rsplit(".", 1)[-1] == cls]
    assert homonymes == [cle], (
        "le build porte desormais %d enum(s) nommes `%s` : %s -- l'appariement par nom PLEIN est "
        "toujours ce qui protege, mais la case-doc affirme l'unicite et doit etre relue"
        % (len(homonymes), cls, homonymes))


# ───────────────────── ETAGE 5 : LA GARDE DEPORTEE de `services/static_battle_rules.py`

def test_etage5_le_littéral_sous_cycle_d_import_vaut_toujours_son_membre():
    """LE CYCLE A DISPARU, ET LA CONVERSION EST FAITE -- cet etage a change de sujet (#484).

    Redaction d'origine : « `services/static_battle_rules.py` ne PEUT PAS importer `EffectType`
    -- cycle MESURE ; son `et == 0x3a` reste donc en littéral, et la garde est ICI ». L'etage
    etait ecrit pour se RETOURNER le jour ou le cycle disparaitrait, et il l'a fait :
    `980173f9` (#270-r4-r2) a ferme le cycle et pose l'import en tete du module, **sans**
    convertir le littéral ni retirer l'etage. Il rougissait depuis, sur `master`, en disant
    exactement quoi faire.

    L'etage garde desormais le RESULTAT de cette conversion, dans les deux sens :
      * le module importe bien `EffectType` (le cycle est ferme, la garde deportee n'a plus
        lieu d'etre) ;
      * et il ne compare plus a un ORDINAL NU -- c'est le cliquet qui empeche la regression."""
    from engine.services.static_battle_rules import (_DARKNESS_EXEMPT_TRAIT_IDS,
                                                     not_blocking_movement_of_traits)

    assert int(EffectType.Darkness) == 0x3a, (
        "`EffectType.Darkness` a change d'ordinal : le littéral 0x3a de "
        "`static_battle_rules.not_blocking_movement_of_traits` designe maintenant AUTRE CHOSE")
    assert not_blocking_movement_of_traits(EffectType.Darkness) == _DARKNESS_EXEMPT_TRAIT_IDS
    # DISCRIMINE : un autre EffectType ne rend PAS la branche Darkness.
    assert not_blocking_movement_of_traits(EffectType.Contaminated) == ()

    # Lu par AST, PAS par recherche de texte : le module CITE l'import dans sa prose (encadre
    # explicatif) -- un `in src` ne distingue pas la citation de l'instruction.
    arbre = ast.parse((ENGINE / "services" / "static_battle_rules.py").read_text(encoding="utf-8"))
    importe = [al.name for n in ast.walk(arbre) if isinstance(n, (ast.Import, ast.ImportFrom))
               for al in n.names]
    assert "EffectType" in importe, (
        "`services/static_battle_rules.py` n'importe plus `EffectType` : si le cycle est revenu, "
        "c'est la CAUSE qu'il faut traiter -- pas ce module qu'il faut re-litteraliser")

    # LE CLIQUET, sur LE SITE dont cet etage a toujours parle. La portee est la FONCTION, pas le
    # module : `get_piercing_ratio` y compare une valeur de degat a `0`, qui ne DESIGNE rien --
    # « hors regle, c'est un scalaire » est un resultat valable, et un cliquet de module le
    # rougirait a tort.
    fn = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)
              and n.name == "not_blocking_movement_of_traits")
    nus = sorted({n.comparators[0].value
                  for n in ast.walk(fn) if isinstance(n, ast.Compare)
                  and len(n.comparators) == 1
                  and isinstance(n.comparators[0], ast.Constant)
                  and isinstance(n.comparators[0].value, int)
                  and not isinstance(n.comparators[0].value, bool)})
    assert nus == [], (
        "`not_blocking_movement_of_traits` compare a des ordinaux NUS %r -- le cycle etant "
        "ferme, ils doivent passer par leur membre d'enum" % (nus,))


# ─────────────── ETAGE 6 : NON-DEGENERESCENCE de l'attribution `1013` (la faute EVITEE)

def test_etage6_confondre_le_KIND_1013_avec_une_ActiveAbilityType_serait_SILENCIEUX():
    """La fausse attribution que la tranche a REFUSEE, mesuree.

    `entities/triggers.IsNormalAttack` compare a `NORMAL_ATTACK_KIND` (0x3f5), qui est un
    `AbilityOrEffect` du decompile -- pas un `ActiveAbilityType`. Or 1013 EST un membre valide
    d'`ActiveAbilityType` : l'y convertir aurait RESOLU, n'aurait rien casse, et aurait ecrit le
    mauvais concept. Le test l'ecrit -- et ASSERTIONNE SON PROPRE NON-VIDE : un controle qui rend
    un ensemble vide passerait pour vert (lecon de #270-r1-r1-r3, etage 5)."""
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND, REGULAR_ATTACK_ABILITY_TYPES

    assert NORMAL_ATTACK_KIND == 0x3f5 == 1013

    # (a) La confusion serait SILENCIEUSE : l'ordinal resout des DEUX cotes.
    resolubles = {v for v in (NORMAL_ATTACK_KIND,)
                  if v in {int(m) for m in ActiveAbilityType}}
    assert resolubles, ("`1013` ne resout plus dans `ActiveAbilityType` : le risque a change de "
                        "forme, relire l'attribution de `entities/triggers.IsNormalAttack`")
    assert ActiveAbilityType(NORMAL_ATTACK_KIND).name == "PrecisionShot_Attack", (
        "l'ordinal 1013 ne nomme plus `PrecisionShot_Attack` : la mesure qui justifie de NE PAS "
        "convertir ce site a change, relire la case-doc")

    # (b) ... et ce n'est PAS le meme concept : `PrecisionShot_Attack` n'est meme pas dans
    #     l'ensemble des attaques REGULIERES que la 1re branche d'`IsNormalAttack` teste.
    assert NORMAL_ATTACK_KIND not in {int(m) for m in REGULAR_ATTACK_ABILITY_TYPES}, (
        "1013 est entre dans `REGULAR_ATTACK_ABILITY_TYPES` : la disjonction des deux branches "
        "d'`IsNormalAttack` est devenue degeneree, relire le decompile")

    # (c) Le site LIT bien le foyer nomme, et il DISCRIMINE.
    from engine.entities.triggers import IsNormalAttack

    class _Ctx:
        def __init__(self, t):
            self.attack_ability_type = t

    assert IsNormalAttack().should_trigger(_Ctx(NORMAL_ATTACK_KIND)) is True
    assert IsNormalAttack().should_trigger(_Ctx(int(ActiveAbilityType.NovaBoost))) is False
    assert IsNormalAttack().should_trigger(_Ctx(None)) is False


def test_etage6b_le_site_1013_lit_le_foyer_NOMME_et_pas_un_ActiveAbilityType():
    """LE CRAN QUE (a)-(c) NE DONNENT PAS -- et il a fallu une CONTRE-EPREUVE pour le voir.

    La premiere version de cet etage se contentait de (a)-(c). Or la mutation exacte qu'il pretend
    interdire -- reecrire le site `ctx.attack_ability_type == int(ActiveAbilityType.PrecisionShot_Attack)`
    -- le laissait VERT : les trois volets mesurent des VALEURS, et la valeur, elle, est la meme
    (1013 des deux cotes). C'est la definition meme d'une confusion SILENCIEUSE EN ORDINAL,
    reproduite a l'interieur de la garde censee l'empecher.

    Le seul canal ou la faute est visible est donc le NOM ECRIT AU SITE : on lit l'AST de
    `IsNormalAttack.should_trigger` et on exige `NORMAL_ATTACK_KIND`, en interdisant tout
    `ActiveAbilityType.<X>`."""
    arbre = ast.parse((ENGINE / "entities" / "triggers.py").read_text(encoding="utf-8"))
    corps = None
    for n in ast.walk(arbre):
        if isinstance(n, ast.ClassDef) and n.name == "IsNormalAttack":
            for st in n.body:
                if isinstance(st, ast.FunctionDef) and st.name == "should_trigger":
                    corps = st
    assert corps is not None, "`IsNormalAttack.should_trigger` a disparu d'`entities/triggers.py`"

    noms = {x.id for x in ast.walk(corps) if isinstance(x, ast.Name)}
    attributs = {"%s.%s" % (x.value.id, x.attr) for x in ast.walk(corps)
                 if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)}
    assert "NORMAL_ATTACK_KIND" in noms, (
        "`IsNormalAttack.should_trigger` ne lit plus `NORMAL_ATTACK_KIND` : le site a ete reecrit, "
        "et si c'est vers un membre d'enum la faute est INVISIBLE EN VALEUR (1013 des deux cotes)")
    fautifs = sorted(a for a in attributs if a.split(".")[0].endswith("ActiveAbilityType")
                     or a.startswith("_AAT."))
    assert not fautifs, (
        "`IsNormalAttack.should_trigger` designe %s : 1013 est bien un `ActiveAbilityType` valide "
        "(`PrecisionShot_Attack`), mais le decompile nomme ce littéral `AbilityOrEffect 0x3f5` -- "
        "un marqueur de KIND. La conversion RESOUT et ecrit le mauvais concept." % fautifs)


# ────────────────────────── CE QUI RESTE EN LITTERAL, ET QUI A ETE VU (pas un oubli)

SCALAIRES_ASSUMES = (
    # (module, attribut, valeur) -- des QUANTITES, pas des designateurs. Le test verifie qu'ils
    # sont restes des `int` PURS : si l'un devenait un membre d'enum, c'est que quelqu'un a force
    # un nom sur un entier qui n'en designe aucun, et la case-doc doit etre relue.
    #
    # ⚠ PORTEE MESUREE (contre-epreuve #270-r4) : les deux entrees lues par `.get(cle, defaut)`
    # (`ELEVATION_BONUS_PCT`, `CONTAMINATED_ARMOR_REDUCTION_PCT`) gardent la valeur EFFECTIVE --
    # muter leur DEFAUT les laisse VERTES, parce que la cle existe au gameconfig et que le defaut
    # n'est jamais atteint. Ce n'est pas un trou : c'est ce qu'elles peuvent garder, et le dire
    # vaut mieux que de laisser croire qu'elles figent le littéral du site.
    ("engine.services.static_battle_rules", "W_LASCANNON_PIERCE_BONUS", 50),
    ("engine.runner.prng", "_N", 624),
    ("engine.runner.prng", "_M", 397),
    ("engine.battle_query", "DISTANCE_UNREACHABLE", 0x7FFFFFFF),
    ("engine.services.movement_query", "INT_MAX", 0x7FFFFFFF),
    # (`fire.FIRE_OF_ABSOLUTION_IGNITE_CHANCE = 30` vivait ici -- RETIREE par #951 : le port LIT
    #  desormais la constante du gameconfig (`fire.fire_of_absolution_ignite_chance()`), comme le
    #  natif (`GetNumberConstant(AbilityConstantType.chance)`). Plus de litteral au site, donc plus
    #  rien a figer.)
    ("engine.runner.operations.triggers.effect_triggers",
     "CONTAMINATED_ARMOR_REDUCTION_PCT", 30),
    ("engine.services.damage_modifiers", "ELEVATION_BONUS_PCT", 50),
    # `MachineOfWarPosition.Bottom` = 2, mais ces deux-la sont deja DERIVES du mirror (#477-r15) ;
    # on garde leur valeur sous cliquet pour que la derivation reste verifiee.
    ("engine.runner.abilities.ultramarines", "MACHINE_POSITION_BOTTOM", 2),
    ("engine.runner.abilities.blacklegion", "DO_MACHINE_POSITION_BOTTOM", 2),
)


def test_les_scalaires_assumes_sont_restes_des_entiers_purs():
    """« Hors regle, c'est un scalaire » est un RESULTAT -- ce test l'ecrit de facon EXECUTABLE."""
    fautes = []
    for mod, attr, attendu in sorted(SCALAIRES_ASSUMES):
        v = importlib.import_module(mod)
        for p in attr.split("."):
            v = getattr(v, p)
        if isinstance(v, Enum):
            fautes.append("%s.%s est devenu %r : un nom a ete force sur une QUANTITE"
                          % (mod, attr, v))
        elif int(v) != attendu:
            fautes.append("%s.%s vaut %d, la tranche avait mesure %d"
                          % (mod, attr, int(v), attendu))
    assert not fautes, "\n  ".join(fautes)


def test_la_borne_de_direction_de_battle_query_reste_une_BORNE():
    """`if direction > 5 or direction < 0` -- le `5` BORNE l'enum `Corner`, il ne DESIGNE pas.

    L'ecrire `int(Corner.SouthEast)` serait forcer un nom : on ne compare pas a SouthEast, on
    verifie l'appartenance au domaine. Le test rend le raisonnement EXECUTABLE -- il mesure que
    `5` est bien le dernier ordinal de `Corner`, ce qui est la seule chose que la borne affirme."""
    ordinaux = sorted(int(m) for m in Corner)
    assert ordinaux == [0, 1, 2, 3, 4, 5], ordinaux
    assert max(ordinaux) == 5, (
        "`Corner` ne s'arrete plus a 5 : la borne `direction > 5` de "
        "`engine/battle_query.get_tiles_in_triangle_shape` laisse desormais passer un membre "
        "valide (ou en refuse un) -- la relire au decompile")

    from engine.battle_query import get_tiles_in_triangle_shape
    # DISCRIMINE : dans le domaine -> 3 coordonnees ; hors domaine -> l'ancre seule.
    for m in Corner:
        assert len(get_tiles_in_triangle_shape((3, 3), int(m))) == 3, m
    assert get_tiles_in_triangle_shape((3, 3), 6) == [(3, 3)]
    assert get_tiles_in_triangle_shape((3, 3), -1) == [(3, 3)]
