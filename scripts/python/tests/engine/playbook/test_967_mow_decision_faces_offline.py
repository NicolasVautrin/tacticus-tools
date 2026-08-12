"""#967 -- garde OFFLINE des SIX faces DECISION des trois MACHINES OF WAR.

Ce que ce fichier FIGE, et pourquoi chaque etage existe :

  0. INSCRIPTION + SEUILS. Les six sont dans `PLAYBOOKS`, avec le `MIN_UTILITY` de leur `.cctor`
     et le `PRIORITY` du sweep #170. Ce sont des valeurs LUES au decompile : un renumerotage du
     build ne doit pas les faire glisser en silence. `2` (1213) et `-1000` (1223) sont les deux
     seules valeurs qui sortent du lot -- ce sont aussi les deux qui changent le comportement.
  1. LA FORME DE L'UTILITE, terme a terme, sur un contexte SYNTHETIQUE. Chaque assertion porte sur
     une valeur ATTENDUE calculee a la main depuis le corps natif, jamais sur « ce que le port
     rend ».
  2. LES CONTRE-EPREUVES. Chacune MUTE l'etat et exige que le resultat CHANGE. Une contre-epreuve
     qui ne mord pas est un vert qui ment (#957 en a eu quatre) : chaque `assert` de mutation est
     donc precede de la mesure du temoin, et l'inegalite est assertionnee.
  3. L'ORDRE DES CIBLES. `Bucket.AddAction` ne remplace que sur `>` STRICT : a utilite egale c'est
     la PREMIERE cible enumeree qui gagne. Le second cran de #957 (`tgt_ids` en `set`, argmax
     decide par le HACHAGE) est garde ici par une epreuve d'INVERSION : permuter `fromHere` doit
     changer la cible emise.

AUCUN runner : tout est offline, `NCContext` est bati a la main.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from engine import battle_query as bq                              # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.playbook import noncomparable as NC                    # noqa: E402
from engine.playbook.noncomparable import _targets as TGT          # noqa: E402

DOTW = int(ActiveAbilityType.DeathOnTheWind)              # 1213
HAILSTRIKE = int(ActiveAbilityType.Hailstrike)            # 1214
MALLEUS = int(ActiveAbilityType.MalleusRocketLauncher)    # 1142
SPOTTER = int(ActiveAbilityType.ForwardSpotter)           # 1143
BEAM = int(ActiveAbilityType.ReanimationBeam)             # 1223
NANO = int(ActiveAbilityType.NanoscarabRepairProtocols)   # 1224

#: `MIN_UTILITY` (le `.cctor`) et `PRIORITY` (sweep exhaustif #170), LUS au decompile.
ATTENDU = {
    DOTW:       ("DeathOnTheWindPlaybook", 2.0, 1000),
    HAILSTRIKE: ("HailstrikePlaybook", 1.0, 0),
    MALLEUS:    ("MalleusRocketLauncherPlaybook", 1.0, 0),
    SPOTTER:    ("ForwardSpotterPlaybook", 1.0, 0),
    BEAM:       ("ReanimationBeamPlaybook", 1.0, -1000),
    NANO:       ("NanoscarabRepairProtocolsPlaybook", 1.0, 0),
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


def _targets_rpc(ability_id: int, entries: list):
    """Callable `ctx.ability_targets` : rend `entries` (deja au format `fromHere`) pour CE couple."""
    def _f(uid, aid):
        if aid != ability_id:
            return {}
        return {"units": [{"unitId": uid,
                           "abilities": [{"abilityId": aid, "fromHere": list(entries)}]}]}
    return _f


def _ctx(ability_id: int, entries: list, *, epos=(), fpos=(), units=(), plans=None,
         enemies=None, tile_ids=None):
    neigh = _neigh()
    walk = {p: True for p in neigh}
    return NC.NCContext(
        uid=1, origin=None, reach_nc=[], epos=list(epos), fpos=list(fpos),
        plan={}, hp_cur_by_id={},
        ability_targets=_targets_rpc(ability_id, entries),
        enemies=list(enemies if enemies is not None
                     else [{"id": 900 + i, "pos": {"col": p[0], "row": p[1]}}
                           for i, p in enumerate(epos)]),
        neigh_by_pos=neigh, walkable_by_pos=walk, obs_units=[], elev_by_pos={},
        tile_id_by_pos=dict(tile_ids or {}), units=list(units), plans=dict(plans or {}))


def _tile_entry(pos, tid):
    return {"kind": "tile", "targetId": tid, "tile": {"col": pos[0], "row": pos[1]}}


def _unit_entry(uid, pos=None):
    e = {"kind": "unit", "targetId": uid}
    if pos is not None:
        e["pos"] = {"col": pos[0], "row": pos[1]}
    return e


# --------------------------------------------------------------------------------------------- #
#  ETAGE 0 -- inscription et seuils
# --------------------------------------------------------------------------------------------- #

def test_les_six_sont_inscrites_avec_leurs_seuils_lus():
    assert len(ATTENDU) == 6, "temoin non degenere : la table doit couvrir les six faces"
    for aid, (cls, minu, prio) in ATTENDU.items():
        pb = NC.PLAYBOOKS.get(aid)
        assert pb is not None, "ability %d absente de PLAYBOOKS" % aid
        assert type(pb).__name__ == cls
        assert pb.MIN_UTILITY == minu, "%d : MIN_UTILITY %s != %s (le .cctor)" % (
            aid, pb.MIN_UTILITY, minu)
        assert pb.PRIORITY == prio, "%d : PRIORITY %s != %s (sweep #170)" % (
            aid, pb.PRIORITY, prio)
    # les deux valeurs qui SORTENT du lot -- ce sont elles qui changent le comportement.
    assert NC.PLAYBOOKS[DOTW].MIN_UTILITY == 2.0
    assert NC.PLAYBOOKS[BEAM].PRIORITY == -1000
    assert NC.PLAYBOOKS[DOTW].PRIORITY == 1000
    # et elles doivent etre les SEULES a sortir (sinon la table ci-dessus a ete recopiee de travers)
    autres = [a for a in ATTENDU if a not in (DOTW,)]
    assert all(NC.PLAYBOOKS[a].MIN_UTILITY == 1.0 for a in autres)


def test_le_tier_de_reanimation_beam_est_sous_le_tier_de_nanoscarab():
    """1224 (tier 0) PRIME sur 1223 (tier -1000) par l'ORDRE des generateurs, pas par l'utilite.

    Contre-epreuve executable du paragraphe : sur le MEME porteur, `choose_action` du tier 0 rend
    1224 et celui du tier -1000 rend 1223 -- deux generateurs distincts, jamais en concurrence."""
    class _Scene:
        def attack_current(self, uid):
            return {50: 700}.get(uid, 0)

    abilities = [{"id": NANO, "usable": True}, {"id": BEAM, "usable": True}]

    def _rpc(uid, aid):
        return {"units": [{"unitId": uid, "abilities": [
            {"abilityId": aid, "fromHere": [_unit_entry(50)]}]}]}

    ctx = _ctx(NANO, [])
    ctx.ability_targets = _rpc
    ctx.scene = _Scene()
    t0 = NC.choose_action(abilities, ctx, priority=0)
    tlast = NC.choose_action(abilities, ctx, priority=-1000)
    assert t0 is not None and t0["ability"] == NANO and t0["pred"] == 700
    assert tlast is not None and tlast["ability"] == BEAM and tlast["pred"] == 1.0
    assert t0["ability"] != tlast["ability"], "temoin degenere : les deux tiers rendent la meme"


# --------------------------------------------------------------------------------------------- #
#  ETAGE 1 -- 1223 / 1224 (necroReanimator)
# --------------------------------------------------------------------------------------------- #

def test_reanimation_beam_utilite_constante_et_keep_first():
    pb = NC.PLAYBOOKS[BEAM]
    ctx = _ctx(BEAM, [_unit_entry(11), _unit_entry(12), _unit_entry(13)])
    out = pb.generate_candidates(ctx)
    assert out and out[0]["pred"] == 1.0 and out[0]["target"] == 11
    # ORDRE : inverser `fromHere` doit changer la cible emise (utilite CONSTANTE -> keep-first).
    ctx2 = _ctx(BEAM, [_unit_entry(13), _unit_entry(12), _unit_entry(11)])
    out2 = pb.generate_candidates(ctx2)
    assert out2 and out2[0]["target"] == 13
    assert out[0]["target"] != out2[0]["target"], (
        "contre-epreuve MUETTE : l'ordre du selecteur ne decide pas l'argmax "
        "-> l'enumeration est passee par un conteneur non ordonne")


def test_nanoscarab_utilite_est_l_attaque_et_pas_les_pv():
    """`GetStat(target, 0, 0, 0)` -- l'ordinal 0 est **ATTACK**. Le squelette est IDENTIQUE a
    `MindControlPlaybook`, qui lit `5 = HEALTH` : confondre les deux serait SILENCIEUX."""
    pb = NC.PLAYBOOKS[NANO]

    class _Scene:
        def __init__(self, atk):
            self._a = atk

        def attack_current(self, uid):
            return self._a.get(uid, 0)

    ctx = _ctx(NANO, [_unit_entry(21), _unit_entry(22)])
    ctx.scene = _Scene({21: 300, 22: 900})
    ctx.hp_cur_by_id = {21: 5000, 22: 10}          # les PV disent l'INVERSE de l'attaque
    out = pb.generate_candidates(ctx)
    assert out and out[0]["target"] == 22 and out[0]["pred"] == 900.0
    # contre-epreuve : si le port lisait les PV, il emettrait 21. Il n'y a qu'a inverser
    # l'ATTAQUE pour que la cible bascule -- et elle DOIT basculer.
    ctx2 = _ctx(NANO, [_unit_entry(21), _unit_entry(22)])
    ctx2.scene = _Scene({21: 900, 22: 300})
    ctx2.hp_cur_by_id = {21: 5000, 22: 10}
    out2 = pb.generate_candidates(ctx2)
    assert out2 and out2[0]["target"] == 21
    assert out[0]["target"] != out2[0]["target"], "contre-epreuve MUETTE sur l'axe ATTAQUE"


def test_nanoscarab_sans_predicteur_ne_fabrique_pas_d_utilite():
    """`ctx.scene is None` -> aucun candidat. Un `0` invente tomberait sous MIN_UTILITY = 1 et
    ferait DISPARAITRE l'ability, mais par un chemin qui ne se voit pas."""
    pb = NC.PLAYBOOKS[NANO]
    ctx = _ctx(NANO, [_unit_entry(21)])
    ctx.scene = None
    assert pb.generate_candidates(ctx) == []


# --------------------------------------------------------------------------------------------- #
#  ETAGE 2 -- 1142 MalleusRocketLauncher
# --------------------------------------------------------------------------------------------- #

def test_malleus_occupant_plus_ou_moins_trois_et_voisins_plus_ou_moins_un():
    pb = NC.PLAYBOOKS[MALLEUS]
    cible = (5, 5)
    ring = [p for p in _neigh()[cible]]
    # occupant ennemi (+3) + 2 ennemis adjacents (+2) - 1 allie adjacent (-1) = 4
    epos = [cible, ring[0], ring[1]]
    fpos = [ring[2]]
    ctx = _ctx(MALLEUS, [_tile_entry(cible, 700)], epos=epos, fpos=fpos)
    out = pb.generate_candidates(ctx)
    assert out and out[0]["target"] == 700
    assert out[0]["pred"] == 4.0, "attendu +3 (occupant ennemi) +2 (voisins) -1 (allie) = 4"


def test_malleus_refuse_un_tir_a_dominante_amie():
    """Gate INLINE `util > Fix64(0)` : occupant ALLIE (-3) + 1 ennemi adjacent (+1) = -2 -> rien."""
    pb = NC.PLAYBOOKS[MALLEUS]
    cible = (5, 5)
    ring = _neigh()[cible]
    ctx = _ctx(MALLEUS, [_tile_entry(cible, 700)], epos=[ring[0]], fpos=[cible])
    assert pb.generate_candidates(ctx) == []
    # contre-epreuve : le MEME etat en retournant l'occupant en ENNEMI doit, lui, produire.
    ctx2 = _ctx(MALLEUS, [_tile_entry(cible, 700)], epos=[cible, ring[0]], fpos=[])
    out2 = pb.generate_candidates(ctx2)
    assert out2 and out2[0]["pred"] == 4.0, (
        "contre-epreuve MUETTE : retourner le camp de l'occupant ne change pas le verdict")


def test_malleus_choisit_la_grappe_la_plus_ennemie_et_garde_le_premier_au_tie():
    pb = NC.PLAYBOOKS[MALLEUS]
    neigh = _neigh()
    a, b = (3, 3), (8, 8)
    epos = [a, b] + neigh[a][:1] + neigh[b][:3]
    ctx = _ctx(MALLEUS, [_tile_entry(a, 701), _tile_entry(b, 702)], epos=epos)
    out = pb.generate_candidates(ctx)
    assert out and out[0]["target"] == 702 and out[0]["pred"] == 6.0   # 3 + 3 voisins
    # TIE : deux tuiles a utilite EGALE -> la PREMIERE de `fromHere` gagne, et permuter bascule.
    epos_tie = [a, b] + neigh[a][:1] + neigh[b][:1]
    c1 = _ctx(MALLEUS, [_tile_entry(a, 701), _tile_entry(b, 702)], epos=epos_tie)
    c2 = _ctx(MALLEUS, [_tile_entry(b, 702), _tile_entry(a, 701)], epos=epos_tie)
    o1, o2 = pb.generate_candidates(c1), pb.generate_candidates(c2)
    assert o1 and o2 and o1[0]["pred"] == o2[0]["pred"] == 4.0
    assert o1[0]["target"] == 701 and o2[0]["target"] == 702
    assert o1[0]["target"] != o2[0]["target"], "contre-epreuve MUETTE sur l'ordre au tie"


# --------------------------------------------------------------------------------------------- #
#  ETAGE 3 -- 1143 ForwardSpotter
# --------------------------------------------------------------------------------------------- #

def test_forward_spotter_a_un_PLANCHER_de_1_la_ou_alpha_warrior_veto():
    """Le `Fix64(1)` POSE AVANT la boucle : une cible sans AUCUNE tuile de spawn utile reste
    EMISE (util 1 >= MIN 1). `AlphaWarriorPlaybook`, meme slot 195, emet le booleen NU -> 0 et
    disparait. C'est la difference que ce test FIGE."""
    pb = NC.PLAYBOOKS[SPOTTER]
    allie = (5, 5)
    # AUCUN ennemi sur le plateau -> slot 195 faux partout -> util = le seul plancher.
    ctx = _ctx(SPOTTER, [_unit_entry(31, allie)], epos=[], fpos=[allie])
    out = pb.generate_candidates(ctx)
    assert out and out[0]["target"] == 31 and out[0]["pred"] == 1.0
    # contre-epreuve : `AlphaWarriorPlaybook` sur le MEME contexte de tuile rend, lui, FAUX.
    from engine.playbook.noncomparable import summon_attack_range as SAR
    assert SAR.has_summon_target_in_attack_range_at_tile(
        ctx, (5, 6), "astraSmnGuardsman", machine_parent=True) is False


def test_forward_spotter_compte_les_tuiles_de_spawn_utiles():
    """util = 1 + #tuiles libres adjacentes a la cible d'ou le Cadian aurait une cible."""
    pb = NC.PLAYBOOKS[SPOTTER]
    allie_a, allie_b = (3, 3), (9, 9)
    ennemi = (3, 5)                      # a portee (2) de plusieurs voisins de `allie_a` seulement
    ctx = _ctx(SPOTTER, [_unit_entry(31, allie_a), _unit_entry(32, allie_b)],
               epos=[ennemi], fpos=[allie_a, allie_b])
    out = pb.generate_candidates(ctx)
    assert out, "aucun candidat : le plancher aurait du en garantir un"
    assert out[0]["target"] == 31, "la cible proche de l'ennemi doit gagner"
    assert out[0]["pred"] > 1.0, (
        "temoin DEGENERE : l'utilite est restee au plancher, donc le comptage n'a rien mesure")
    # contre-epreuve : retirer l'ennemi doit ramener les DEUX cibles au plancher, donc rendre
    # l'argmax indifferent -> keep-first sur la 1re de `fromHere`.
    ctx2 = _ctx(SPOTTER, [_unit_entry(32, allie_b), _unit_entry(31, allie_a)],
                epos=[], fpos=[allie_a, allie_b])
    out2 = pb.generate_candidates(ctx2)
    assert out2 and out2[0]["pred"] == 1.0 and out2[0]["target"] == 32
    assert out[0]["pred"] != out2[0]["pred"], "contre-epreuve MUETTE sur le comptage"


def test_forward_spotter_prend_la_branche_MACHINE_du_slot_195():
    """`astraOrdnanceBattery` est une MoW -> `HasSummonTargetInAttackRangeAtTileWithMachineParent`,
    qui teste TOUS les ennemis. La branche UNITE ne teste que le plus PROCHE : sur un etat ou le
    plus proche est hors de portee et un autre y est, les deux branches DIVERGENT -- et c'est
    exactement le residu #945-r1 que ce port ferme."""
    from engine.playbook.noncomparable import summon_attack_range as SAR
    tile = (5, 5)
    # `astraSmnGuardsman` : portee max de ses armes (gameconfig). Le plus PROCHE ennemi est place
    # a une distance qui passe, un second beaucoup plus loin -- on verifie d'abord que la branche
    # machine repond VRAI des qu'UN ennemi passe.
    ctx = _ctx(SPOTTER, [], epos=[(5, 6), (11, 11)])
    assert SAR.has_summon_target_in_attack_range_at_tile(
        ctx, tile, "astraSmnGuardsman", machine_parent=True) is True
    # etat ou AUCUN ennemi n'est a portee : les deux branches doivent dire FAUX (temoin non degenere)
    loin = _ctx(SPOTTER, [], epos=[(11, 11)])
    assert SAR.has_summon_target_in_attack_range_at_tile(
        loin, tile, "astraSmnGuardsman", machine_parent=True) is False
    assert SAR.has_summon_target_in_attack_range_at_tile(
        loin, tile, "astraSmnGuardsman", machine_parent=False) is False


# --------------------------------------------------------------------------------------------- #
#  ETAGE 4 -- 1213 DeathOnTheWind
# --------------------------------------------------------------------------------------------- #

def _dotw_line(aim, direction, n):
    walkable_at, elevation_at, tile_exists = bq.tiles_behind_accessors(None, None)
    return bq.get_tiles_behind(aim, direction, max_count=n - 1, check_walkable=False,
                               update_reference=True, walkable_at=walkable_at,
                               elevation_at=elevation_at, tile_exists=tile_exists)


def test_death_on_the_wind_compte_la_cible_plus_la_meilleure_ligne():
    """util = 1 (occupant de la tuile visee) + #ennemis sur la ligne la mieux peuplee du ring-1,
    **trous compris** (aucun `FilterContinuous`, contrairement a 1187)."""
    pb = NC.PLAYBOOKS[DOTW]
    n = pb._nr_of_tiles()
    assert n == 3, "nrOfTiles lu au gameconfig (i2 : « 3 hexes long ») ; mesure = %r" % n
    aim = (5, 5)
    ring = bq.get_surrounding_tiles(aim, radius=1, include_center=False, check_walkable=True)
    assert ring, "temoin degenere : anneau vide"
    ligne = _dotw_line(aim, ring[0], n)
    assert len(ligne) == n - 1, "la ligne doit etre BORNEE a nrOfTiles-1 : %r" % (ligne,)
    # ennemi sur la cible + ennemi sur la SECONDE tuile de la ligne (la 1re restant VIDE) : sans
    # FilterContinuous le trou ne casse PAS le compte.
    epos = [aim, ligne[1]]
    ctx = _ctx(DOTW, [_tile_entry(aim, 800)], epos=epos, tile_ids={aim: 800})
    out = pb.generate_candidates(ctx)
    assert out and out[0]["target"] == 800
    assert out[0]["pred"] == 2.0, (
        "attendu 1 (cible) + 1 (ennemi DERRIERE un trou) = 2 ; un FilterContinuous rendrait 1")


def test_death_on_the_wind_min_utility_2_refuse_la_cible_isolee():
    """Un SEUL ennemi (l'occupant de la tuile visee) donne util 1 < MIN_UTILITY 2 -> rien."""
    pb = NC.PLAYBOOKS[DOTW]
    aim = (5, 5)
    ctx = _ctx(DOTW, [_tile_entry(aim, 800)], epos=[aim], tile_ids={aim: 800})
    assert pb.generate_candidates(ctx) == []
    # contre-epreuve : ajouter UN ennemi sur une tuile de ligne doit suffire a produire.
    ring = bq.get_surrounding_tiles(aim, radius=1, include_center=False, check_walkable=True)
    ligne = _dotw_line(aim, ring[0], pb._nr_of_tiles())
    ctx2 = _ctx(DOTW, [_tile_entry(aim, 800)], epos=[aim, ligne[0]], tile_ids={aim: 800})
    out2 = pb.generate_candidates(ctx2)
    assert out2 and out2[0]["pred"] == 2.0, (
        "contre-epreuve MUETTE : le seuil 2 ne separe rien sur cet etat")


def test_death_on_the_wind_gate_should_evaluate_exige_un_ennemi_adjacent():
    """`HasPossibleTarget` : il faut une tuile ciblable ayant >= 1 ennemi ADJACENT."""
    pb = NC.PLAYBOOKS[DOTW]
    aim = (5, 5)
    loin = (0, 0)
    ctx_seul = _ctx(DOTW, [_tile_entry(aim, 800)], epos=[aim, loin], tile_ids={aim: 800})
    assert pb.should_evaluate(ctx_seul) is False
    ring = _neigh()[aim]
    ctx_grappe = _ctx(DOTW, [_tile_entry(aim, 800)], epos=[aim, ring[0]], tile_ids={aim: 800})
    assert pb.should_evaluate(ctx_grappe) is True
    assert pb.should_evaluate(ctx_seul) != pb.should_evaluate(ctx_grappe), (
        "contre-epreuve MUETTE : le gate ne discrimine pas")


def test_death_on_the_wind_gate_ne_refuse_pas_a_l_aveugle():
    """Canal `epos` MUET -> `True` : un gate qui REFUSE ne doit jamais le faire sur du non-mesure."""
    pb = NC.PLAYBOOKS[DOTW]
    ctx = _ctx(DOTW, [_tile_entry((5, 5), 800)], epos=[], tile_ids={(5, 5): 800})
    assert pb.should_evaluate(ctx) is True


# --------------------------------------------------------------------------------------------- #
#  ETAGE 5 -- 1214 Hailstrike
# --------------------------------------------------------------------------------------------- #

def test_hailstrike_le_bonus_de_500_domine_le_terme_de_percage():
    """`bonus` (0 ou 500) contre `100 - PiercingRatio` (borne par 100) : aucun percage ne peut
    renverser une classe de bonus. Ce test FIGE cette domination -- c'est elle qui rend le terme
    aleatoire NON PORTE (#967-r3) inoffensif sur la classe."""
    pb = NC.PLAYBOOKS[HAILSTRIKE]
    assert pb.RANGED_BONUS > pb.PIERCE_BASE + 10, (
        "la domination du bonus n'est plus structurelle -- le residu #967-r3 change de portee")
    assert pb.RNG_TERM == 0.0, "le terme aleatoire doit rester une BORNE, jamais une moyenne"


def test_hailstrike_prefere_l_allie_au_plus_faible_percage():
    """`100 - PiercingRatio` : l'utilite DECROIT avec le percage deja possede."""
    pb = NC.PLAYBOOKS[HAILSTRIKE]
    import gameconfig as gc

    # deux unites REELLES du gameconfig dont les profils d'arme different en PiercingRatio.
    def _pierce(vid):
        w = (gc.unit(gc.resolve_unit_id(vid) or vid) or {}).get("weapons") or []
        r = next((x for x in w if x.get("Range")), None) or (w[0] if w else None)
        if not r or not r.get("DamageProfile"):
            return None
        return (gc.damage_profile(r["DamageProfile"]) or {}).get("PiercingRatio")

    paires = []
    for vid in ("custoBladeChampion", "astraSmnGuardsman", "necroWarrior", "orksBoy",
                "tyranTermagant", "ultraEliminator", "bloodTerminator", "darkaCompanion"):
        p = _pierce(vid)
        if p is not None:
            paires.append((vid, p))
    valeurs = sorted({p for _v, p in paires})
    assert len(valeurs) >= 2, (
        "temoin DEGENERE : aucune paire de PiercingRatio distincts trouvee dans le gameconfig "
        "-- le test ne mesurerait rien (%r)" % (paires,))
    bas = next(v for v, p in paires if p == valeurs[0])       # percage FAIBLE -> utilite FORTE
    haut = next(v for v, p in paires if p == valeurs[-1])     # percage FORT   -> utilite FAIBLE
    units = [{"id": 41, "visualId": haut, "pos": {"col": 1, "row": 1}},
             {"id": 42, "visualId": bas, "pos": {"col": 2, "row": 2}}]
    ctx = _ctx(HAILSTRIKE, [_unit_entry(41), _unit_entry(42)], units=units)
    out = pb.generate_candidates(ctx)
    assert out, "aucun candidat"
    assert out[0]["target"] == 42, (
        "l'allie au percage le plus FAIBLE (%s) doit gagner sur %s" % (bas, haut))
    assert pb._pierce_utility(bas) > pb._pierce_utility(haut), "temoin DEGENERE sur le percage"


def test_hailstrike_bonus_overwatch_bascule_la_cible():
    """`HasTrait(target, Overwatch)` -> 500, quel que soit le percage. Contre-epreuve : la MEME
    paire sans le trait rend l'AUTRE cible."""
    pb = NC.PLAYBOOKS[HAILSTRIKE]
    import gameconfig as gc
    porteurs = [u for u in (gc.all_unit_ids() or {}).get("lineup", [])
                if "Overwatch" in ((gc.unit(u) or {}).get("traits") or [])]
    if not porteurs:
        pytest.skip("aucune unite `Overwatch` dans le gameconfig de ce build -- rien a mesurer")
    ow = porteurs[0]
    units = [{"id": 51, "visualId": "custoBladeChampion", "pos": {"col": 1, "row": 1}},
             {"id": 52, "visualId": ow, "pos": {"col": 2, "row": 2}}]
    ctx = _ctx(HAILSTRIKE, [_unit_entry(51), _unit_entry(52)], units=units)
    out = pb.generate_candidates(ctx)
    assert out and out[0]["target"] == 52 and out[0]["pred"] >= pb.RANGED_BONUS
    # contre-epreuve : le porteur d'Overwatch SEUL contre lui-meme sans trait -> l'ecart DOIT
    # exister, sinon le bonus n'a pas mordu.
    sans = pb._ranged_bonus(ctx, 51, "custoBladeChampion")
    avec = pb._ranged_bonus(ctx, 52, ow)
    assert avec == pb.RANGED_BONUS and avec != sans, (
        "contre-epreuve MUETTE : le bonus Overwatch ne separe pas (%s vs %s)" % (avec, sans))


# --------------------------------------------------------------------------------------------- #
#  ETAGE 6 -- le lecteur de cibles ne perd pas l'ordre
# --------------------------------------------------------------------------------------------- #

def test_le_lecteur_de_cibles_rend_une_LISTE_ordonnee():
    """`_targets` doit rendre une sequence ORDONNEE, jamais un ensemble : l'argmax de
    `Bucket.AddAction` (remplacement STRICT) depend de l'ordre du selecteur natif."""
    ctx = _ctx(BEAM, [_unit_entry(9), _unit_entry(3), _unit_entry(7)])
    got = TGT.eligible_units(ctx, BEAM)
    assert isinstance(got, list)
    assert [t for t, _p in got] == [9, 3, 7], (
        "l'ordre du selecteur n'est pas preserve : %r" % (got,))
    ctxt = _ctx(DOTW, [_tile_entry((1, 1), 61), _tile_entry((2, 2), 62)],
                tile_ids={(1, 1): 61, (2, 2): 62})
    assert [t for _p, t in TGT.eligible_tiles(ctxt, DOTW)] == [61, 62]
