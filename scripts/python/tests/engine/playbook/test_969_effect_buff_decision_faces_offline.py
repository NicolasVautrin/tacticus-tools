"""#969 -- garde OFFLINE des CINQ faces DECISION de categorie EFFECT/BUFF.

Ce que ce fichier FIGE, etage par etage :

  0. INSCRIPTION + SEUILS. Les cinq sont dans `PLAYBOOKS`, avec le `MIN_UTILITY` de leur `.cctor`
     et le `PRIORITY` du sweep #170 (les cinq sont hors table -> tier 0). Valeurs LUES au
     decompile : un renumerotage du build ne doit pas les faire glisser en silence.
  1. LA FORME DE CHAQUE UTILITE, terme a terme, sur un contexte SYNTHETIQUE. Les valeurs attendues
     sont calculees A LA MAIN depuis le corps natif, jamais recopiees de ce que le port rend.
  2. LES DEUX AXES DE VARIATION, et ils ne sont pas les memes selon l'ability. `1049` et `1228`
     varient avec la POSITION du caster (et doivent donc DEPLACER le caster) ; `1003` et `1203`
     varient avec la CIBLE ; `1106` ne varie de rien. Chaque contre-epreuve MESURE le temoin puis
     exige que le resultat CHANGE -- une contre-epreuve qui ne mord pas est un vert qui ment.
  3. L'AXE SUR LEQUEL CHACUNE NE VARIE PAS. C'est le cran symetrique, et c'est celui que #957 et
     #967 ont paye : pour `1228`, l'utilite est calculee DANS la boucle des cibles mais argumentee
     par `e.CasterPosition` -- elle ne peut donc RIEN departager entre cibles. On l'assertionne.
  4. LES GATES `should_evaluate`, et surtout leur ASYMETRIE : `1049`, `1106` et `1003` ont un ZERO
     DETERMINISTE (porte) ; `1228` n'en a PAS (les deux valeurs de son `GetUseProbability` sont
     strictement positives) -- son `True` constant est donc une LECTURE, pas un oubli. Un canal
     MUET ne doit jamais faire refuser (le trou silencieux de #967).
  5. L'ORDRE DES CIBLES. `Bucket$$AddAction` ne remplace que sur `>` STRICT -> a utilite egale,
     la PREMIERE cible enumeree gagne. Epreuve d'INVERSION (le second cran de #957 : `set` ->
     l'argmax decide par le HACHAGE).
  6. LE GAMECONFIG que `1049` LIT (`constants["range"]`), avec assertion de son propre NON-VIDE.

AUCUN runner : tout est offline, `NCContext` est bati a la main.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.playbook import noncomparable as NC                    # noqa: E402
from engine.playbook.noncomparable import crusade_of_wrath as COW   # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: Trop LARGE est sain, trop ETROIT est un FAUX VERT -- on prend donc TOUT ce que les cinq
#: playbooks lisent, y compris les foyers geometriques et le gameconfig.
DECLENCHEUR = {
    "chemins": (
        # LES CINQ FACES -- ce que le fichier garde directement.
        "scripts/python/engine/playbook/noncomparable/crusade_of_wrath.py",
        "scripts/python/engine/playbook/noncomparable/daemonic_patrons.py",
        "scripts/python/engine/playbook/noncomparable/death_from_above.py",
        "scripts/python/engine/playbook/noncomparable/sternguard_focus.py",
        "scripts/python/engine/playbook/noncomparable/war_howl.py",
        # LE FOYER DE LECTURE DES CIBLES (ordre natif, liste jamais `set`).
        "scripts/python/engine/playbook/noncomparable/_targets.py",
        # LE REGISTRE et la BASE : une ability retiree de `PLAYBOOKS`, un `native_priority`
        # renumerote, un `NCContext` ampute ou un `_will_normal_attack_kill` deplace changent
        # le verdict.
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        # LE GATE PARTAGE de 1203 : son foyer est cote Comparable.
        "scripts/python/engine/playbook/base.py",
        # LA GEOMETRIE. DEUX etages DISTINCTS et non interchangeables : `adjacent_addable_count`
        # / `is_adjacent` (voisinage STOCKE + porte d'elevation) pour 1003 et 1228, et le
        # DISQUE GEOMETRIQUE de `hexgeo.distance` pour 1049 (`GetSurroundingUnits`).
        "scripts/python/engine/battle_query.py",
        "scripts/python/hexgeo.py",
        # LA FACTION, foyer partage de `HasFaction` lu par 1228.
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        # LES MIRRORS D'ENUM cites au site.
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        # LE GAMECONFIG : `constants["range"]` de 1049 est LU a l'execution (etage 6).
        "scripts/python/gameconfig.py",
        # LA SONDE DE MORSURE : elle ancre ses mutations sur des lignes EXACTES de ces fichiers ;
        # si elle change, la valeur de ce garde change avec elle.
        "scripts/python/probe_969_morsure.py",
    ),
    # Le fichier LIT le gameconfig du build courant (`constants["range"]` de `CrusadeOfWrath`).
    # Un changement de build change donc ce qu'il mesure -- etage 6, qui assertionne son non-vide.
    "build": True,
    "toujours": False,
    "raison": (
        "Garde des cinq faces DECISION #969 : seuils du `.cctor`, tiers `get_Priority`, forme de "
        "chaque utilite, AXE de variation (position vs cible) et son symetrique (l'axe sur lequel "
        "elle ne varie PAS), gates `should_evaluate` et leur asymetrie, ORDRE du selecteur. Tout "
        "ce qui precede entre dans son verdict, plus le gameconfig du build -- d'ou `build: True`."),
}

COW_ID = int(ActiveAbilityType.CrusadeOfWrath)     # 1049
PATRONS = int(ActiveAbilityType.DaemonicPatrons)   # 1203
DFA = int(ActiveAbilityType.DeathFromAbove)        # 1003
STERN = int(ActiveAbilityType.SternguardFocus)     # 1228
HOWL = int(ActiveAbilityType.WarHowl)              # 1106

#: `MIN_UTILITY` (le `.cctor`) et `PRIORITY` (sweep exhaustif #170 : les cinq sont HORS table).
ATTENDU = {
    COW_ID:  ("CrusadeOfWrathPlaybook", 1.0, 0),
    PATRONS: ("DaemonicPatronsPlaybook", 1.0, 0),
    DFA:     ("DeathFromAbovePlaybook", 1.0, 0),
    STERN:   ("SternguardFocusPlaybook", 1.0, 0),
    HOWL:    ("WarHowlPlaybook", 1.0, 0),
}


# --------------------------------------------------------------------------------------------- #
#  Substrat synthetique
# --------------------------------------------------------------------------------------------- #

def _neigh(cols=12, rows=12) -> dict:
    """Voisinage NATIF d'un plateau plat, derive de `hexgeo` (le meme que `bq` consomme)."""
    import hexgeo
    out = {}
    for c in range(cols):
        for r in range(rows):
            out[(c, r)] = [(x, y) for (x, y) in hexgeo.disk(c, r, 1)
                           if (x, y) != (c, r) and 0 <= x < cols and 0 <= y < rows]
    return out


def _targets_rpc(ability_id: int, from_here: list, targets: list | None = None):
    """Callable `ctx.ability_targets`. `from_here` = la vue PAR POSITION (l'ordre natif du
    selecteur) ; `targets` = l'UNION sur les tuiles de move (slot 69). Les deux ne sont PAS
    interchangeables -- 1106 et 1003 lisent l'UNION, tout le reste lit `fromHere`."""
    def _f(uid, aid):
        if aid != ability_id:
            return {}
        return {"units": [{"unitId": uid,
                           "abilities": [{"abilityId": aid,
                                          "fromHere": list(from_here),
                                          "targets": list(from_here if targets is None
                                                          else targets)}]}]}
    return _f


def _ctx(*, uid=1, origin=(0, 0), reach=((0, 0),), epos=(), fpos=(), obs=(), units=(),
         ability_targets=None, hp=None, scene=None):
    neigh = _neigh()
    return NC.NCContext(
        uid=uid, origin=origin, reach_nc=list(reach), epos=list(epos), fpos=list(fpos),
        plan={}, hp_cur_by_id=dict(hp or {}), ability_targets=ability_targets,
        neigh_by_pos=neigh, walkable_by_pos={p: True for p in neigh},
        elev_by_pos={p: 0 for p in neigh}, obs_units=list(obs), units=list(units), scene=scene)


def _unit(uid, col, row, vis=None, dead=False):
    return {"id": uid, "squadId": uid, "visualId": vis, "col": col, "row": row, "isDead": dead}


# --------------------------------------------------------------------------------------------- #
#  ETAGE 0 -- inscription, seuils, tiers, hierarchie
# --------------------------------------------------------------------------------------------- #

@pytest.mark.parametrize("aid", sorted(ATTENDU))
def test_etage0_inscription_seuil_et_tier(aid):
    """Les cinq sont dans `PLAYBOOKS` avec le `MIN_UTILITY` de leur `.cctor` et le tier `0`.

    `MIN_UTILITY = 1` vient de `<Playbook>$$.cctor` -> `Fix64.op_Implicit(1)` pour les cinq (relu
    un par un ; celui de 1049 ecrit DEUX statiques, dont ce `1`). `PRIORITY = 0` = les cinq sont
    ABSENTES de `NATIVE_PRIORITY` (22 entrees, sweep exhaustif #170)."""
    nom, minu, prio = ATTENDU[aid]
    pb = NC.playbook_for(aid)
    assert pb is not None, f"{aid} absente de PLAYBOOKS -- le moteur ne proposerait JAMAIS l'ability"
    assert type(pb).__name__ == nom
    assert pb.MIN_UTILITY == minu
    assert pb.PRIORITY == prio
    assert aid not in NC.NATIVE_PRIORITY, f"{aid} entree dans NATIVE_PRIORITY -> re-lire le sweep"


def test_etage0_base_non_comparable():
    """Les cinq heritent de `NonComparablePlaybook` -- la hierarchie LUE dans `frida/classes.tsv`.

    ⚠ Le `.ctor` decompile en `ComparablePlaybook<...>..ctor` pour les CINQ (corps gshared
    DEDUPLIQUE, mislabele) : c'est la STRUCTURE qui tranche, jamais le nom. La fiche `#893-r1` du
    backlog avait recopie ce faux nom pour 1049 -- ce test est ce qui empeche de le re-croire."""
    for aid in ATTENDU:
        assert isinstance(NC.playbook_for(aid), NC.NonComparablePlaybook)


# --------------------------------------------------------------------------------------------- #
#  ETAGE 1 + 2 -- 1049 CrusadeOfWrath : utilite = #allies buffes, POSITION-dependante
# --------------------------------------------------------------------------------------------- #

def test_etage1_cow_utilite_est_le_compte_des_allies_dans_le_rayon():
    """`utilite = <statics+0x00> * Count(GetBuffTargets(Entity(caster), Entity(tile)))`.

    Rayon LU au gameconfig (`constants["range"]`, = 2 sur ce build). Contexte : trois allies a
    distance <= 2 de l'origine et un QUATRIEME a distance 3 -> l'attendu, calcule a la main, est
    `3.0` et non `4.0`."""
    r = COW._buff_range()
    assert r is not None and r >= 1, "rayon non mesurable -> l'etage ne mesure rien"
    # (1,0) d=1 ; (2,0) d=2 ; (1,1) d=1 ; (r+2,0) d=r+2 -> HORS rayon.
    ctx = _ctx(fpos=[(1, 0), (2, 0), (1, 1), (r + 2, 0)])
    out = NC.playbook_for(COW_ID).generate_candidates(ctx)
    assert len(out) == 1
    assert out[0]["pred"] == 3.0, "le 4e allie, hors rayon, ne doit PAS etre compte"
    assert out[0]["target"] == ctx.uid, "la cible emise est le CASTER (self-cast)"
    assert out[0]["to"] is None, "utilite egale a l'origine -> keep-first, pas de deplacement"


def test_etage2_cow_varie_avec_la_position_et_deplace_le_caster():
    """CONTRE-EPREUVE de l'axe POSITION. Le selecteur est RECONSTRUIT avec la tuile candidate
    (`GetBuffTargetsSelector(caster, tile)`), donc l'utilite en depend -- malgre un
    `AbilityEntities` bati hors de toute boucle. C'est le piege de #957, ici dans le bon sens.

    TEMOIN d'abord (allies groupes autour de l'origine -> il reste), puis MUTATION (les memes
    allies deplaces autour d'une tuile de move -> il doit BOUGER)."""
    pb = NC.playbook_for(COW_ID)
    reach = [(0, 0), (6, 0)]
    temoin = pb.generate_candidates(_ctx(reach=reach, fpos=[(1, 0), (1, 1)]))
    assert temoin and temoin[0]["to"] is None and temoin[0]["pred"] == 2.0

    mute = pb.generate_candidates(_ctx(reach=reach, fpos=[(7, 0), (6, 1)]))
    assert mute, "aucun candidat apres mutation -> la contre-epreuve ne mesure rien"
    assert mute[0]["to"] == (6, 0), "l'utilite doit DEPLACER le caster vers ses allies"
    assert mute[0]["to"] != temoin[0]["to"], "MUTATION SANS EFFET : rien ne tient cet axe"


def test_etage2_cow_include_center_exclut_la_tuile_candidate():
    """`SurroundingUnits(..., includeCenter = 0, ...)` : la tuile candidate ELLE-MEME est hors du
    compte (`d >= 1`).

    ⚠ **CE TERME EST INERTE DANS TOUT REGIME ATTEIGNABLE, ET C'EST POUR CA QU'IL FAUT L'ECRIRE
    ICI.** Le caster occupe l'origine, et une tuile de move est libre par construction : aucune
    partie ne peut poser un allie sur la tuile candidate. La sonde `probe_969_morsure` a d'abord
    rendu cette mutation MUETTE -- le terme etait juste, transcrit du natif, et tenu par RIEN. On
    l'attaque donc au niveau du helper, sur un etat volontairement IMPOSSIBLE en partie : c'est le
    seul endroit d'ou le terme est observable."""
    pb = NC.playbook_for(COW_ID)
    r = COW._buff_range()
    ctx = _ctx(fpos=[(0, 0), (1, 0)])          # un allie SUR la tuile candidate, un a d=1
    assert pb._buff_targets_count(ctx, (0, 0), r) == 1, (
        "la tuile candidate doit etre EXCLUE (includeCenter = 0)")
    assert pb._buff_targets_count(ctx, (5, 5), r) == 0   # temoin : loin de tout


def test_etage2_cow_disque_geometrique_pas_le_voisinage_stocke():
    """`SurroundingUnits` descend sur `TileQuery$$IterateSurroundingTiles` (triple boucle cube) --
    disque GEOMETRIQUE, SANS porte d'elevation ni liste d'adjacence stockee (mesure de
    `GrotTankPlaybook` r=3 et de `ThriceBlessedConflagrationPlaybook` r=1).

    CONTRE-EPREUVE : on AMPUTE `neigh_by_pos` et `elev_by_pos`. Un port qui aurait cable
    `bq.is_adjacent` (le foyer des `GetAdjacent*`) verrait son compte bouger ; le compte
    geometrique, lui, ne doit PAS bouger."""
    pb = NC.playbook_for(COW_ID)
    plein = _ctx(fpos=[(1, 0), (2, 0), (1, 1)])
    ampute = _ctx(fpos=[(1, 0), (2, 0), (1, 1)])
    ampute.neigh_by_pos, ampute.elev_by_pos = {}, {}
    a = pb.generate_candidates(plein)
    b = pb.generate_candidates(ampute)
    assert a and b and a[0]["pred"] == b[0]["pred"] == 3.0


# --------------------------------------------------------------------------------------------- #
#  ETAGE 1 + 2 -- 1228 SternguardFocus : 1 + 10, POSITION-dependante, CIBLE-independante
# --------------------------------------------------------------------------------------------- #

def _ctx_stern(*, reach, fpos, vis, cibles):
    obs = [_unit(9 + i, p[0], p[1], vis=vis) for i, p in enumerate(fpos)]
    return _ctx(reach=reach, fpos=fpos, obs=obs,
                ability_targets=_targets_rpc(STERN, cibles))


def test_etage1_stern_bonus_dark_angel_adjacent():
    """`utilite = Fix64(1)`, `+ Fix64(10)` si un AUTRE Dark Angel ami est adjacent a la position."""
    cibles = [{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]
    sans = _ctx_stern(reach=[(0, 0)], fpos=[(4, 4)], vis="darkaSternguard", cibles=cibles)
    avec = _ctx_stern(reach=[(0, 0)], fpos=[(1, 0)], vis="darkaSternguard", cibles=cibles)
    pb = NC.playbook_for(STERN)
    a = pb.generate_candidates(sans)
    b = pb.generate_candidates(avec)
    assert a and a[0]["pred"] == 1.0, "aucun DA adjacent -> le plancher seul"
    assert b and b[0]["pred"] == 11.0, "un DA adjacent -> 1 + 10"


def test_etage2_stern_la_faction_mord():
    """CONTRE-EPREUVE de `HasFaction(u, 10 = DarkAngels)` : le MEME voisin, d'une AUTRE faction,
    ne doit PAS donner le bonus. Sans ce cran, le port compterait n'importe quel allie adjacent."""
    cibles = [{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]
    pb = NC.playbook_for(STERN)
    da = pb.generate_candidates(
        _ctx_stern(reach=[(0, 0)], fpos=[(1, 0)], vis="darkaSternguard", cibles=cibles))
    autre = pb.generate_candidates(
        _ctx_stern(reach=[(0, 0)], fpos=[(1, 0)], vis="ultraInceptorSgt", cibles=cibles))
    assert da and autre
    assert da[0]["pred"] == 11.0 and autre[0]["pred"] == 1.0
    assert da[0]["pred"] != autre[0]["pred"], "MUTATION SANS EFFET : la faction n'est pas lue"


def test_etage3_stern_utilite_INDEPENDANTE_de_la_cible():
    """L'AXE SUR LEQUEL ELLE NE VARIE PAS -- le cran symetrique de #957.

    `HasAdjacentDarkAngels(caster, e.CasterPosition)` est calcule DANS la boucle des cibles, ce qui
    donne l'illusion qu'il les departage ; son argument est la position du CASTER, identique pour
    tous les elements d'un meme appel. Deux jeux de cibles TRES differents doivent donc rendre la
    MEME utilite -- seule la cible EMISE change (keep-first)."""
    pb = NC.playbook_for(STERN)
    a = pb.generate_candidates(_ctx_stern(
        reach=[(0, 0)], fpos=[(1, 0)], vis="darkaSternguard",
        cibles=[{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]))
    b = pb.generate_candidates(_ctx_stern(
        reach=[(0, 0)], fpos=[(1, 0)], vis="darkaSternguard",
        cibles=[{"kind": "unit", "targetId": 3, "pos": {"col": 9, "row": 1}},
                {"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]))
    assert a and b
    assert a[0]["pred"] == b[0]["pred"], "l'utilite de 1228 ne doit PAS dependre de la cible"
    assert b[0]["target"] == 3, "a utilite egale, la PREMIERE cible enumeree gagne"


def test_etage5_stern_ordre_des_cibles_est_une_LISTE():
    """EPREUVE D'INVERSION (le second cran de #957) : permuter `fromHere` doit changer la cible
    emise. Si le port passait par un `set`, l'argmax serait decide par le HACHAGE."""
    pb = NC.playbook_for(STERN)
    c1 = [{"kind": "unit", "targetId": 3, "pos": {"col": 9, "row": 1}},
          {"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]
    a = pb.generate_candidates(_ctx_stern(reach=[(0, 0)], fpos=[(1, 0)],
                                          vis="darkaSternguard", cibles=c1))
    b = pb.generate_candidates(_ctx_stern(reach=[(0, 0)], fpos=[(1, 0)],
                                          vis="darkaSternguard", cibles=list(reversed(c1))))
    assert a and b and a[0]["target"] == 3 and b[0]["target"] == 7
    assert a[0]["target"] != b[0]["target"], "l'ordre du selecteur n'est pas preserve"


# --------------------------------------------------------------------------------------------- #
#  ETAGE 1 + 2 -- 1003 DeathFromAbove : utilite = #tuiles de spawn autour de la CIBLE
# --------------------------------------------------------------------------------------------- #

def _ctx_dfa(cibles, *, epos=(), fpos=(), targets=None):
    return _ctx(reach=[(0, 0)], epos=epos, fpos=fpos,
                ability_targets=_targets_rpc(DFA, cibles, targets))


def test_etage1_dfa_utilite_est_le_compte_de_tuiles_libres():
    """`utilite = Count(CanAddUnit(AdjacentTiles(cible)))`. Plateau plat, cible en (5,5) : six
    voisins, tous libres -> `6.0` (calcule a la main, pas releve du port)."""
    out = NC.playbook_for(DFA).generate_candidates(
        _ctx_dfa([{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]))
    assert out and out[0]["pred"] == 6.0 and out[0]["target"] == 7
    assert out[0]["to"] is None, "utilite position-INDEPENDANTE -> le caster ne bouge pas"


def test_etage2_dfa_les_tuiles_occupees_mordent():
    """CONTRE-EPREUVE : occuper deux voisins de la cible doit FAIRE BAISSER l'utilite de 2."""
    pb = NC.playbook_for(DFA)
    cible = [{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]
    libre = pb.generate_candidates(_ctx_dfa(cible))
    import hexgeo
    voisins = [p for p in hexgeo.disk(5, 5, 1) if p != (5, 5)][:2]
    bouche = pb.generate_candidates(_ctx_dfa(cible, epos=voisins))
    assert libre and bouche
    assert bouche[0]["pred"] == libre[0]["pred"] - 2, "les tuiles occupees ne sont pas retirees"
    assert bouche[0]["pred"] != libre[0]["pred"], "MUTATION SANS EFFET"


def test_etage2_dfa_argmax_sur_la_cible_la_plus_degagee():
    """L'AXE CIBLE : entre deux ennemis, celui qui a le PLUS de place autour gagne."""
    import hexgeo
    cibles = [{"kind": "unit", "targetId": 3, "pos": {"col": 2, "row": 2}},
              {"kind": "unit", "targetId": 7, "pos": {"col": 8, "row": 8}}]
    # on bouche 3 voisins du PREMIER -> le second doit l'emporter malgre le keep-first
    bouches = [p for p in hexgeo.disk(2, 2, 1) if p != (2, 2)][:3]
    out = NC.playbook_for(DFA).generate_candidates(_ctx_dfa(cibles, fpos=bouches))
    assert out and out[0]["target"] == 7, "l'argmax doit suivre le compte, pas l'ordre"


# --------------------------------------------------------------------------------------------- #
#  ETAGE 1 + 2 -- 1203 DaemonicPatrons : utilite = PV, gate WillNormalAttackKill
# --------------------------------------------------------------------------------------------- #

def test_etage1_patrons_utilite_est_les_pv_courants():
    """`utilite = Fix64(GetStat(target, 5 = Health, 0 = Current, null))`."""
    pb = NC.playbook_for(PATRONS)
    ctx = _ctx(hp={7: 1234})
    assert pb.evaluate_non_comparable((0, 0), 7, ctx) == 1234.0
    assert pb.evaluate_non_comparable((0, 0), 99, ctx) is None, "PV inconnus -> pas de candidat"


def test_etage2_patrons_le_gate_will_normal_attack_kill_mord(monkeypatch):
    """CONTRE-EPREUVE du `continue` natif : quand l'attaque NORMALE sure-kill la cible, le playbook
    la SAUTE. Ce gate est le SEUL discriminant de 1203 -- sans lui, l'utilite (les PV) classerait
    simplement l'ennemi le plus gros, y compris celui qu'il fallait laisser a l'attaque normale.

    Le foyer patche est `engine.playbook.base.will_normal_attack_kill` (forme B/C : le differe de
    `_base._will_normal_attack_kill` re-execute l'import a chaque appel, donc le patch MORD)."""
    pb = NC.playbook_for(PATRONS)
    ctx = _ctx(hp={7: 1234})
    temoin = pb.evaluate_non_comparable((0, 0), 7, ctx)
    assert temoin == 1234.0, "temoin DEGENERE : le gate n'aurait rien a annuler"

    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill",
                        lambda ctx_, tgt, pos: True)
    mute = pb.evaluate_non_comparable((0, 0), 7, ctx)
    assert mute is None, "MUTATION SANS EFFET : le gate `WillNormalAttackKill` n'est pas cable"
    assert mute != temoin


def test_etage2_patrons_le_gate_est_position_dependant(monkeypatch):
    """Le gate predit l'attaque normale DEPUIS la position candidate : deux tuiles peuvent donc
    rendre des verdicts differents pour la MEME cible. On le figure explicitement."""
    pb = NC.playbook_for(PATRONS)
    ctx = _ctx(hp={7: 500})
    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill",
                        lambda ctx_, tgt, pos: pos == (0, 0))
    assert pb.evaluate_non_comparable((0, 0), 7, ctx) is None
    assert pb.evaluate_non_comparable((3, 0), 7, ctx) == 500.0


# --------------------------------------------------------------------------------------------- #
#  ETAGE 1 -- 1106 WarHowl : utilite PLATE, cible = le CASTER
# --------------------------------------------------------------------------------------------- #

def test_etage1_howl_utilite_plate_sur_le_caster():
    """`utilite = Fix64(1)` reconstruit a chaque tour de boucle, sans AUCUN terme ; cible = le
    caster (self-cast, `RANGE_SELF`) ; pas de deplacement (utilite plate -> keep-first)."""
    ctx = _ctx(reach=[(0, 0), (3, 0)], ability_targets=_targets_rpc(
        HOWL, [{"kind": "unit", "targetId": 1}]))
    out = NC.playbook_for(HOWL).generate_candidates(ctx)
    assert out == [{"target": 1, "ability": HOWL, "to": None, "pred": 1.0}]


def test_etage1_howl_pas_de_candidat_si_le_self_cast_est_refuse():
    """Le selecteur natif ne rend RIEN quand la cascade de ciblage refuse le cast (cooldown,
    `CasterHasNotMoved`, `CasterMatchesDynamicRule`) -> aucun candidat."""
    ctx = _ctx(ability_targets=_targets_rpc(HOWL, []))
    assert NC.playbook_for(HOWL).generate_candidates(ctx) == []


# --------------------------------------------------------------------------------------------- #
#  ETAGE 4 -- les gates `should_evaluate`, et leur ASYMETRIE
# --------------------------------------------------------------------------------------------- #

def test_etage4_howl_zero_deterministe_sans_cible_dattaque_normale():
    """`GetUseProbability(unit)` rend `Fix64(0)` quand l'UNION des cibles d'attaque normale (slot
    69, sur TOUTES les tuiles de move) est vide -> `ShouldEvaluate` FALSE.

    TEMOIN : une cible presente -> True. MUTATION : plus aucune -> False."""
    pb = NC.playbook_for(HOWL)
    unites = [{"id": 1, "pos": {"col": 0, "row": 0},
               "abilities": [{"id": 77, "kind": "normal"}]}]
    avec = _ctx(units=unites, ability_targets=_targets_rpc(77, [{"kind": "unit", "targetId": 7}]))
    sans = _ctx(units=unites, ability_targets=_targets_rpc(77, []))
    assert pb.should_evaluate(avec) is True, "temoin DEGENERE"
    assert pb.should_evaluate(sans) is False, "le ZERO deterministe de 1106 n'est pas porte"


def test_etage4_howl_lit_l_UNION_pas_la_vue_par_position():
    """Le natif interroge le slot `69 GetAllValidTargetsFromAllPossibleMovementTiles` -- l'UNION
    sur toutes les tuiles de move. `fromHere`, lui, n'enumere que depuis l'origine.

    ⚠ **LES DEUX VUES NE SONT PAS INTERCHANGEABLES, ET LE GARDE NE LE VOYAIT PAS** : la sonde
    `probe_969_morsure` a rendu la mutation `targets -> fromHere` MUETTE, parce que le substrat de
    test remplissait les deux vues a l'identique. On les fait ici DIVERGER : aucune cible depuis
    l'origine, une cible depuis une tuile de move. Un port qui lirait `fromHere` refuserait le cast
    -- alors que le natif l'accepte, Ragnar n'ayant qu'a avancer d'un hex."""
    pb = NC.playbook_for(HOWL)
    unites = [{"id": 1, "pos": {"col": 0, "row": 0},
               "abilities": [{"id": 77, "kind": "normal"}]}]
    divergent = _ctx(units=unites, reach=[(0, 0), (3, 0)],
                     ability_targets=_targets_rpc(
                         77, [], targets=[{"kind": "unit", "targetId": 7}]))
    assert pb.should_evaluate(divergent) is True, (
        "1106 doit lire l'UNION (slot 69), pas `fromHere`")
    vide = _ctx(units=unites, reach=[(0, 0), (3, 0)],
                ability_targets=_targets_rpc(77, [], targets=[]))
    assert pb.should_evaluate(vide) is False, "temoin DEGENERE : les deux vues vides -> refus"


def test_etage4_howl_canal_muet_ne_refuse_JAMAIS():
    """DEGRADATION PERMISSIVE : sans RPC (ou sans attaque normale identifiable), on rend True.
    Un False a l'aveugle rendrait l'ability INVISIBLE du moteur -- le trou silencieux de #967."""
    pb = NC.playbook_for(HOWL)
    assert pb.should_evaluate(_ctx()) is True                        # ability_targets = None
    assert pb.should_evaluate(_ctx(units=[{"id": 1, "abilities": []}],
                                   ability_targets=_targets_rpc(77, []))) is True


def test_etage4_cow_zero_deterministe_sans_allie_a_portee():
    """`prob = 0.1 * maxBuffed` -> `maxBuffed == 0` fait rendre False. Et un canal MUET
    (`reach_nc` vide) ne doit PAS refuser."""
    pb = NC.playbook_for(COW_ID)
    assert pb.should_evaluate(_ctx(reach=[(0, 0)], fpos=[(1, 0)])) is True   # temoin
    assert pb.should_evaluate(_ctx(reach=[(0, 0)], fpos=[])) is False
    assert pb.should_evaluate(_ctx(reach=[], fpos=[])) is True, "canal muet -> jamais de refus"


def test_etage4_dfa_zero_deterministe():
    """`ShouldEvaluate` PROPRE (surcharge du slot 4) : `GetBestTarget == null` ou
    `GetNumSummons < 1` -> False. La branche `numSummons` passe par `min(turnsStarted, tuiles)`."""
    pb = NC.playbook_for(DFA)
    cible = [{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]
    assert pb.should_evaluate(_ctx_dfa(cible)) is True                       # temoin
    assert pb.should_evaluate(_ctx_dfa([])) is False, "aucune cible -> GetBestTarget == null"

    import hexgeo
    tous = [p for p in hexgeo.disk(5, 5, 1) if p != (5, 5)]
    assert pb.should_evaluate(_ctx_dfa(cible, epos=tous)) is False, "0 tuile libre -> refus"
    assert pb.should_evaluate(_ctx()) is True, "canal muet -> jamais de refus"


def test_etage4_dfa_turns_started_nul_refuse():
    """`GetNumSummons = min(StatAmount(caster, 12 = TURNS_STARTED), tuiles)` : un compteur a `0`
    fait rendre `prob = 0`."""
    class _Scene:
        def __init__(self, ts):
            self._ts = ts

        def turns_started(self, uid):
            return self._ts

    pb = NC.playbook_for(DFA)
    cible = [{"kind": "unit", "targetId": 7, "pos": {"col": 5, "row": 5}}]
    base = dict(reach=[(0, 0)], ability_targets=_targets_rpc(DFA, cible))
    assert pb.should_evaluate(_ctx(scene=_Scene(3), **base)) is True         # temoin
    assert pb.should_evaluate(_ctx(scene=_Scene(0), **base)) is False


def test_etage4_stern_n_a_PAS_de_gate_et_c_est_une_lecture():
    """`...SternguardFocusPlaybook$$GetUseProbability(unit, actionTiles)` rend `0.75` ou un
    statique de `Fix64` -- deux valeurs STRICTEMENT POSITIVES, donc `prob <= 0` n'arrive jamais et
    `ShouldEvaluate` ne refuse PAS. Le `True` constant est une LECTURE, pas un gate oublie.

    C'est l'asymetrie qui compte : trois des cinq ont un zero determin iste, celle-ci non. Un futur
    lecteur qui ajouterait un gate << par symetrie >> casserait ce test."""
    pb = NC.playbook_for(STERN)
    assert pb.should_evaluate(_ctx()) is True
    assert pb.should_evaluate(_ctx(reach=[], fpos=[], epos=[])) is True
    assert type(pb).should_evaluate is NC.NonComparablePlaybook.should_evaluate, (
        "1228 ne doit PAS surcharger le slot 4 : son GetUseProbability n'a pas de zero")


def test_etage4_patrons_n_a_PAS_de_gate_slot4():
    """1203 n'expose que trois corps (`.ctor`, `.cctor`, `EvaluateNonComparable`). L'absence dans
    les tables ne PROUVE pas l'absence de surcharge (dedup des corps triviaux) -- le port rend donc
    le defaut de base, et ce test FIGE ce choix pour qu'il se relise."""
    pb = NC.playbook_for(PATRONS)
    assert type(pb).should_evaluate is NC.NonComparablePlaybook.should_evaluate


# --------------------------------------------------------------------------------------------- #
#  ETAGE 6 -- le gameconfig LU par 1049
# --------------------------------------------------------------------------------------------- #

def test_etage6_rayon_lu_au_gameconfig_et_non_vide():
    """`constants["range"]` de `CrusadeOfWrath` (`GetNumberConstant(0x16)`), LU et non invente.

    ⚠ Le test ASSERTIONNE SON PROPRE NON-VIDE : un rayon `None` ferait passer les etages 1 et 2
    pour verts en ne mesurant rien -- le vice qu'un ensemble vide a deja fait passer pour vert
    (#270-r1-r1-r3)."""
    r = COW._buff_range()
    assert r is not None, "rayon NON MESURE -- les etages 1/2 de 1049 ne mesureraient rien"
    assert r == 2, "l'i2 dit << within 2 hexes >> : un ecart ici = build change, RE a refaire"


def test_etage6_rayon_absent_ne_fait_pas_refuser(monkeypatch):
    """Le TRI-ETAT du rayon : `None` (config muette) ne doit pas se rabattre sur `0`, sinon
    `should_evaluate` refuserait a l'aveugle et l'ability disparaitrait du moteur."""
    pb = NC.playbook_for(COW_ID)
    monkeypatch.setattr(COW, "_buff_range", lambda: None)
    assert pb.should_evaluate(_ctx(reach=[(0, 0)], fpos=[(1, 0)])) is True
    assert pb.generate_candidates(_ctx(reach=[(0, 0)], fpos=[(1, 0)])) == []
