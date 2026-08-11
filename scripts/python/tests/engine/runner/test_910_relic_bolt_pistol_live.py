"""CLIQUET #910 -- les DEUX canaux de la relique `RelicBoltPistol`
(`EffectType` 0x5b1 = 1457 `RelicBoltPistol_ExtraPierce`, 0x5b2 = 1458
`RelicBoltPistol_ExtraCritDamage`).

CRITERE : « le natif ajoute-t-il `extraPierceRatio[niveau de RELIQUE]` au ratio de percage des
attaques MELEE de son porteur et `extraCritDmg[niveau]` a son degat de crit en RANGED, chacun
DOUBLE quand la cible porte `Xenos` ou `Chaos` -- et le port fait-il pareil ? »

Le montage est IMPORTE du probe (`probe_910_relic_bolt_pistol_live.py`) au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale. Le foyer
partage est `flags_de_build`.

CINQ bras, et les quatre derniers sont des contre-epreuves :
  1. LIVE == OFFLINE ;
  2. `NOCHANNEL` (les deux effets retires d'`EFFECT_CLASSES` -> retombee sur `BaseEffect`, canal
     `None`) : doit CHANGER dans les deux canaux. Sans lui, « ca concorde » ne vaudrait rien ;
  3. `NODOUBLE` (`<DSLFormulas+0x28>` ramene a `Direct(1)`) : doit CHANGER **ssi** la cible porte
     `Xenos` ou `Chaos` -- c'est ce qui prouve que le `If` natif est une MAGNITUDE, pas un gate ;
  4. `PASSIF` (le callable `tertiary_ability_state_of` retire des DEUX contextes) : le port retombe
     sur le niveau des PASSIFS. Doit CHANGER des que le niveau demande n'est pas le dernier palier ;
  5. `KIT_TRAITS` (canal PERCAGE) : `target_traits` relu du KIT gameconfig, la vue d'AVANT #910.
     Doit CHANGER ssi la cible porte `Xenos`/`Chaos` -- ces pseudo-traits de GRANDE-ALLIANCE ne
     figurent dans AUCUN `traits` gameconfig, donc le gate y serait MORT ;
  6. `CROISE` (gate de NATURE inverse) : doit CHANGER dans les deux canaux.

⚠ TROIS PIECES DU MONTAGE ECHOUENT EN SILENCE, et les trois ont ete MESUREES :
  * `my_player` derive de la PREMIERE unite vivante du `decisionView` est celui de la CIBLE : le
    tour amene est alors celui du camp adverse, l'attaque part, rend `ok: true` et ne mute RIEN
    (`mutated: false`, `changes: []`) ;
  * une tuile a `hexgeo.distance == 1` mais ABSENTE de la liste d'adjacence STOCKEE donne le MEME
    refus silencieux -- le natif teste l'adjacence par `TileQuery$$IterateAdjacentTiles`, pas par
    la geometrie ;
  * avec `--crit 100,...`, le canal PERCAGE est DEGENERE (le crit ne traverse pas l'armure de la
    meme facon) : `bonus_pierce = 12` cote port et pourtant `NOCHANNEL` ne mord pas. Meme forme de
    piege que l'armure trop FAIBLE, ou `total = base - armure` ne depend plus du percage.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_910_relic_bolt_pistol_live import (  # noqa: E402
    ABILITY_ID, CARRIER, EFFECT_CRIT, EFFECT_PIERCE, TARGET, TRAITS_DOUBLANTS,
    VAR_CRIT, VAR_PIERCE, etages, flags_de_build, paliers, replay, stage, strike)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test live : la cascade des `conftest.py` et le harnais.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/catalog_inject.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/rl_duel.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Le montage vient du probe (foyer `flags_de_build`) ; les deux
        # classes d'effet et leur inscription au registre sont l'objet meme du cliquet ; les
        # deux AGREGATEURS sont les canaux qui les appellent, et `abilities/base.py` porte la
        # reparation #910 (`target_traits` = substrat d'ENTITE + niveau TERTIAIRE).
        "scripts/python/probe_910_relic_bolt_pistol_live.py",
        "scripts/python/engine/entities/effects/loki/relic_bolt_pistol.py",
        # Le paquet `loki` est traverse par la fermeture d'imports (`factory` l'entre) : declare
        # explicitement, sinon `probe_486r15` rougit sur un DECLENCHEUR trop ETROIT.
        "scripts/python/engine/entities/effects/loki/__init__.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/runner/abilities/base.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il confronte les DEUX canaux de la relique au natif : le montage (probe), les deux "
              "classes d'effet et leur registre, les deux agregateurs qui les appellent, le foyer "
              "du niveau TERTIAIRE, et les deux vecteurs de coup (normale melee / normale ranged) "
              "qui threadent `is_ranged` et `target_traits`.",
}

_P_PIERCE = paliers(VAR_PIERCE)
_P_CRIT = paliers(VAR_CRIT)


def _mesure(charge_regime, trait, canal, level=3, board="MC1_67", seed="777"):
    """Monte, frappe, rejoue -- et rend les cinq vues d'un coup. Toute impossibilite de MONTAGE
    LEVE (jamais un skip vert : un echec de montage parti en skip est un VERT QUI MENT)."""
    h = charge_regime(p_units=CARRIER, a_units=TARGET, seed=seed, board=board,
                      extra=flags_de_build(trait, canal, level))
    rec = stage(h, canal)
    live, why = strike(h, rec)
    assert live is not None, "attaque non jouee : %s" % why
    k = len(live)
    off = replay(h, rec)[:k]
    vues = {nom: replay(h, rec, mutate=nom)[:k]
            for nom in ("NOCHANNEL", "NODOUBLE", "PASSIF", "CROISE", "KIT_TRAITS")}
    return rec, live, off, vues, etages(h, rec)


@pytest.mark.parametrize("trait", ["Hero", "Xenos", "Chaos"])
def test_le_canal_percage_double_contre_chaos_ou_xenos(charge_regime, trait):
    """`ForAddition(get_OwnerIsCaster & IsMeleeAttack, If(HasTrait(Target, Xenos|Chaos),
    Multiply(ConfigVar(0x3f), Direct(2)), ConfigVar(0x3f)))`.

    `Hero` est le TEMOIN NEUTRE : la branche FAUSSE du `If`. Il vaut controle NEGATIF pour
    `NODOUBLE` et `KIT_TRAITS`, qui ne doivent alors PAS mordre."""
    level, double = 3, trait in TRAITS_DOUBLANTS
    rec, live, off, vues, et = _mesure(charge_regime, trait, "PIERCE", level)
    assert trait in et["traits_entite_cible"], (
        "le trait ECRIT n'est pas dans le substrat d'ENTITE lu par le port : %s"
        % (et["traits_entite_cible"],))
    assert off == live, "trait=%s : port %s != natif %s (etages %s)" % (trait, off, live, et)
    attendu = _P_PIERCE[level - 1] * (2 if double else 1)
    assert et["bonus_pierce"] == attendu, (
        "bonus de percage du port %s != %d (%s[%d] = %d%s)"
        % (et["bonus_pierce"], attendu, VAR_PIERCE, level, _P_PIERCE[level - 1],
           " x2 par le `If`" if double else ""))
    assert et["bonus_crit"] is None, (
        "en MELEE le canal crit-DEGAT doit se TAIRE (`IsRangedAttack`), il rend %s"
        % (et["bonus_crit"],))
    assert vues["NOCHANNEL"] != off, "le canal doit mordre (mut=%s off=%s)" % (vues["NOCHANNEL"], off)
    assert (vues["NODOUBLE"] != off) is double, (
        "trait=%s : `Direct(2)` doit mordre SSI la cible est Chaos/Xenos (mut=%s off=%s)"
        % (trait, vues["NODOUBLE"], off))
    assert vues["CROISE"] != off, "le gate `IsMeleeAttack` doit mordre"


@pytest.mark.parametrize("trait", ["Hero", "Chaos"])
def test_le_canal_crit_degat_double_contre_chaos_ou_xenos(charge_regime, trait):
    """`ForAddition(get_OwnerIsCaster & IsRangedAttack, If(HasTrait(Target, Xenos|Chaos),
    Multiply(ConfigVar(0x42), Direct(2)), ConfigVar(0x42)))`.

    Le SECOND membre de la disjonction (`Chaos`) est joue ici et le premier (`Xenos`) sur le canal
    PERCAGE : les deux `HasTrait` natifs sont donc exerces."""
    level, double = 3, trait in TRAITS_DOUBLANTS
    rec, live, off, vues, et = _mesure(charge_regime, trait, "CRIT", level)
    assert off == live, "trait=%s : port %s != natif %s (etages %s)" % (trait, off, live, et)
    attendu = _P_CRIT[level - 1] * (2 if double else 1)
    assert et["bonus_crit"] == attendu, (
        "bonus de crit-DEGAT du port %s != %d (%s[%d] = %d%s)"
        % (et["bonus_crit"], attendu, VAR_CRIT, level, _P_CRIT[level - 1],
           " x2 par le `If`" if double else ""))
    assert et["bonus_pierce"] is None, (
        "en RANGED le canal PERCAGE doit se TAIRE (`IsMeleeAttack`), il rend %s"
        % (et["bonus_pierce"],))
    assert vues["NOCHANNEL"] != off, "le canal doit mordre (mut=%s off=%s)" % (vues["NOCHANNEL"], off)
    assert (vues["NODOUBLE"] != off) is double, (
        "trait=%s : `Direct(2)` doit mordre SSI la cible est Chaos/Xenos (mut=%s off=%s)"
        % (trait, vues["NODOUBLE"], off))
    assert vues["CROISE"] != off, "le gate `IsRangedAttack` doit mordre"


def test_le_gate_de_traits_lit_le_substrat_d_entite_pas_le_kit(charge_regime):
    """CLIQUET DE LA REPARATION #910 du canal PERCAGE.

    `HasTrait(Target@DSLSelectors+0x60, ...)` resout par `BaseUnitComponent$$HasTrait`, donc la
    liste EFFECTIVE de l'ENTITE. `ability_pierce_effect_bonus` relisait `gameconfig.unit().traits`
    -- le KIT -- ou `Xenos`/`Chaos` ne figurent POUR AUCUNE UNITE (mesure : 0 sur les trois
    groupes). Le doublement y etait donc structurellement MORT, en silence.

    Le bras `KIT_TRAITS` rejoue cette vue : il doit CHANGER le degat sur une cible Xenos, et NE PAS
    le changer sur le temoin neutre (sans quoi il accuserait autre chose que le substrat)."""
    rec, live, off, vues, et = _mesure(charge_regime, "Xenos", "PIERCE", 3)
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert vues["KIT_TRAITS"] != off, (
        "la vue KIT doit PERDRE le doublement (mut=%s off=%s) -- si elle ne mord pas, ou bien le "
        "kit porte deja le pseudo-trait d'alliance, ou bien le canal ne lit plus `target_traits`"
        % (vues["KIT_TRAITS"], off))
    assert vues["KIT_TRAITS"] == vues["NODOUBLE"], (
        "la vue KIT doit rendre EXACTEMENT le non-double (%s) et non une troisieme valeur (%s)"
        % (vues["NODOUBLE"], vues["KIT_TRAITS"]))


@pytest.mark.parametrize("level", [1, 10])
def test_le_niveau_lu_est_celui_de_la_relique_pas_du_passif(charge_regime, level):
    """`GetAbilityState(effect)` -> l'`AbilityState` **TERTIAIRE** (`BC.Units[].TertiaryAbilityLevel`),
    pas celui des passifs. Le bras `PASSIF` le prouve : il ne peut mordre QUE si le niveau demande
    n'est pas le dernier palier (le repli passif y clampe justement)."""
    rec, live, off, vues, et = _mesure(charge_regime, "Xenos", "PIERCE", level)
    assert off == live, "lvl=%d : port %s != natif %s (etages %s)" % (level, off, live, et)
    assert et["ability_state"][0] == level, (
        "le port lit le niveau %s au lieu de %d -- canal TERTIAIRE non branche"
        % (et["ability_state"], level))
    assert et["bonus_pierce"] == 2 * _P_PIERCE[level - 1], (
        "ConfigVar(0x3f) lu = %s, attendu %d" % (et["bonus_pierce"], 2 * _P_PIERCE[level - 1]))
    assert (vues["PASSIF"] != off) is (level != len(_P_PIERCE)), (
        "lvl=%d : le bras PASSIF doit mordre SSI le niveau n'est pas le dernier palier "
        "(mut=%s off=%s)" % (level, vues["PASSIF"], off))


def test_les_deux_effets_sont_au_registre_avec_leur_identite_de_config():
    """GARDE DE REGISTRE, OFFLINE : les cles `EFFECT_CLASSES` sont les NOMS que publie
    `decisionView`, et la config lue par les DEUX effets est la TRIGGERED 1467 -- pas les
    `EffectType` 1457/1458, qui nomment DEUX AUTRES reliques dans l'enum des triggered. Les cinq
    valeurs sont relues des enums, jamais recopiees."""
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.relic_bolt_pistol import (
        RelicBoltPistolExtraCritDamageEffect, RelicBoltPistolExtraPierceEffect)
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert EFFECT_CLASSES.get(EFFECT_PIERCE) is RelicBoltPistolExtraPierceEffect
    assert EFFECT_CLASSES.get(EFFECT_CRIT) is RelicBoltPistolExtraCritDamageEffect
    assert EffectType(1457).name == EFFECT_PIERCE
    assert EffectType(1458).name == EFFECT_CRIT
    assert TriggeredAbilityType(1467).name == ABILITY_ID
    # LES TROIS COLLISIONS, gardees explicitement : ecrire l'ordinal au lieu du membre nomme aurait
    # lu la config d'une AUTRE relique, sans lever la moindre erreur.
    assert TriggeredAbilityType(1457).name != ABILITY_ID, (
        "1457 en TriggeredAbilityType est une AUTRE relique -- la collision est le piege du cas")
    assert TriggeredAbilityType(1458).name != ABILITY_ID
    assert EffectType(1467).name not in (EFFECT_PIERCE, EFFECT_CRIT)


def test_le_gate_de_traits_porte_sur_les_deux_pseudo_traits_d_alliance():
    """GARDE OFFLINE du couple `(Xenos, Chaos)` : les deux ordinaux sont relus de l'enum du build,
    et l'assertion FIGE le fait qui rend la lecture par le KIT impossible -- AUCUNE unite du
    gameconfig ne porte l'un de ces deux traits dans son `traits`."""
    import gameconfig as GC
    from engine.entities.effects.loki.relic_bolt_pistol import _QUALIFYING_TRAITS
    from engine.entities.traits.unit_trait import UnitTrait
    assert tuple(int(t) for t in _QUALIFYING_TRAITS) == (int(UnitTrait.Xenos), int(UnitTrait.Chaos))
    assert (int(UnitTrait.Xenos), int(UnitTrait.Chaos)) == (1006, 2026)
    porteurs = [u for u in GC.all_unit_ids()
                if {"Xenos", "Chaos"} & set((GC.unit(u) or {}).get("traits") or ())]
    assert porteurs == [], (
        "des unites portent desormais le pseudo-trait d'alliance dans leur KIT (%s) : le bras "
        "KIT_TRAITS du cliquet vivant perdrait sa raison d'etre, a re-mesurer" % porteurs[:5])
