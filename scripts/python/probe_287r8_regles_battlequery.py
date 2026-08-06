"""#287-r8 -- les trois regles dynamiques de ciblage portees par la tranche, MESUREES offline.

Pendant OFFLINE de `probe_287r8_regles_battlequery_live.py` : ici on prouve que chaque regle
DISCRIMINE (bascule) et que le port la CONSULTE reellement (mutants en DELTA) ; le probe live prouve
qu'elle discrimine COMME LE NATIF sur un plateau reel.

Les trois ids, et l'ETAGE que chacun a demande :

  | id   | ability             | canal     | etage                                                |
  |------|---------------------|-----------|------------------------------------------------------|
  | 1025 | SkyStrike           | surcharge | `BattleQuery$$GetAdjacentTiles` (surcharge IList)     |
  | 1087 | ExemplarOfTheKauyon | table     | `BattleQuery$$GetAdjacentUnits` (slot 122)            |
  | 1112 | AlphaWarrior        | surcharge | `SynapseEffect` comme `IAuraEffect` (aura.py)         |

CE QUE CE PROBE CHASSE, ET POURQUOI CHAQUE ETAGE EXISTE.

1. RECENSEMENT -- les trois ids doivent etre EVALUABLES, et par le canal attendu. Une regle rangee
   dans le mauvais canal (surcharge la ou la classe n'existe pas, table la ou la classe existe)
   serait silencieusement ignoree par la cascade.

2. BASCULE -- un couple de substrats par BRAS de chaque regle, qui ne different QUE par la grandeur
   que le corps natif LIT. `1025` en a TROIS (`CasterHasNotMoved` / `TargetHasFreeAdjacentTile` / le
   court-circuit d'adjacence), et c'est le point : il rend DEUX codes de refus distincts, et un port
   qui les confondrait passerait une bascule a deux bras.

3. MUTANTS -- on DESARME la regle et l'on exige que la bascule S'EFFONDRE. Le critere est le DELTA
   (`avant == refus` ET `apres == 0`), jamais `apres == 0` seul : mesure dans cette lignee, la
   seconde forme rendait 5/5 sur un arbre ou AUCUNE regle n'etait portee -- l'inertie de la mutation
   s'y comptait comme un vert.

4. LE CRAN SOUS L'ETAGE -- `SynapseEffect` comme `IAuraEffect`. Sans lui, `GetInRangeAuraAmount`
   rend `0` par cast echoue et `1112` refuse TOUTE cible : un SUR-refus systematique, l'exact
   contraire de la degradation permissive du module. Cet etage se mesure a part, parce qu'il est
   sous la regle et qu'un vert de la bascule ne dirait pas d'ou vient le `0`.

Usage :
    python scripts/python/probe_287r8_regles_battlequery.py
    python scripts/python/probe_287r8_regles_battlequery.py --detail
ASCII only ; exit 0 = les trois regles mordent, et aucune ne s'est mise a mentir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from engine.entities.active_ability_type import ActiveAbilityType              # noqa: E402
from engine.entities.effect_type import EffectType                             # noqa: E402
from engine.entities.effects.aura import (aura_current_range, aura_max_range,  # noqa: E402
                                          aura_next_turn_range, aura_trait, is_aura_effect)
from engine.entities.traits.unit_trait import UnitTrait                        # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR         # noqa: E402
from probe_287r4r1_dynamic_target_rules import (_porteur, desarme,             # noqa: E402
                                                evaluabilite, substrat)

CASTER, CIBLE, ALLIE, ENNEMI = 1, 2, 3, 4

# `substrat()` monte le board `MC1_67` (cf. `probe_287r4r1._board`). Les bascules de cette tranche
# sont SPATIALES : elles ont besoin d'un couple ADJACENT et d'une tuile ELOIGNEE (au-dela de la
# portee Synapse). Ces trois positions sont DERIVEES du board, jamais ecrites en dur -- un triplet
# fige serait faux au premier changement de board, et une bascule posee sur une tuile inexistante
# serait verte par VACUITE (les deux bras y rendraient le meme refus, pour la mauvaise raison).
# L'etape 0 re-verifie l'invariant que la derivation est censee garantir.

def _positions():
    """(A, B, LOIN) : A et B marchables ADJACENTES, LOIN marchable a `d > 2` de A, avec au moins un
    voisin marchable LIBRE (le bras `TargetHasFreeAdjacentTile` de 1025 doit pouvoir basculer)."""
    from probe_287r4r1_dynamic_target_rules import _board
    import hexgeo
    b = _board()
    marchables = sorted(t for t in b.by_id if b.walkable(t))
    for t in marchables:
        ca = b.coord(t)
        vois = [n for n in b.neighbours(t) if b.walkable(n)]
        if len(vois) < 2:
            continue
        cb = b.coord(vois[0])
        for u in marchables:
            cl = b.coord(u)
            if hexgeo.distance(ca, cl) > 2 and len([n for n in b.neighbours(u)
                                                    if b.walkable(n)]) >= 1:
                return ca, cb, cl
    raise RuntimeError("board sans triplet (adjacent, eloigne) -- substrat inutilisable")


A, B, LOIN = _positions()


def _tid(coord):
    from probe_287r4r1_dynamic_target_rules import _board
    return _board().id_at(int(coord[0]), int(coord[1]))


def _regle(aid: int, st, caster_id=CASTER, target_id=CIBLE) -> int:
    return int(_porteur(int(aid)).get_dynamic_invalid_target_reason(st, caster_id, target_id) or 0)


# ================================================================================================
# 0. LE BOARD -- les coordonnees des bascules doivent EXISTER et etre marchables
# ================================================================================================

def verifier_geometrie() -> list:
    """Une bascule SPATIALE posee sur une tuile hors board ou non marchable serait verte par
    vacuite : les deux bras y rendraient le meme refus, pour une raison qui n'est pas la regle."""
    from probe_287r4r1_dynamic_target_rules import _board
    import hexgeo
    b = _board()
    out = []
    for nom, c in (("A", A), ("B", B), ("LOIN", LOIN)):
        tid = b.id_at(int(c[0]), int(c[1]))
        out.append((nom, c, tid is not None, tid is not None and b.walkable(tid)))
    out.append(("d(A,B)", (hexgeo.distance(A, B),), hexgeo.distance(A, B) == 1, True))
    out.append(("d(A,LOIN)", (hexgeo.distance(A, LOIN),), hexgeo.distance(A, LOIN) > 2, True))
    return out


# ================================================================================================
# 1. LES SUBSTRATS -- un par BRAS
# ================================================================================================

def _cas_sky_strike():
    """`1025` -- TROIS bras, parce que le natif rend TROIS verdicts distincts.

    Le corps : `moved && !adjacent -> CasterHasNotMoved` ; `adjacent -> 0` ; sinon
    `GetAdjacentTiles(targetTiles,1,1,0).Count > 0 ? 0 : TargetHasFreeAdjacentTile`.

    Le flag `Moved` passe par `components.set_moved_flag` -- le LECTEUR UNIQUE du port
    (`unit_has_moved` = `UnitFlagsComponent.Has(MOVED)`), donc le meme store que le natif."""
    from engine.runner.components import set_moved_flag
    lo = [(CASTER, "adeptCelestine", 1, A[0], A[1], []),
          (CIBLE, "necroWarden", 2, LOIN[0], LOIN[1], [])]
    ad = [(CASTER, "adeptCelestine", 1, A[0], A[1], []),
          (CIBLE, "necroWarden", 2, B[0], B[1], [])]
    st_moved = substrat(lo)
    set_moved_flag(st_moved, CASTER)                       # a bouge, cible NON adjacente -> 0x10
    st_libre = substrat(lo)                                # n'a pas bouge, tuiles libres -> 0
    st_adj = substrat(ad)
    set_moved_flag(st_adj, CASTER)                         # a bouge MAIS au contact -> 0
    return st_moved, st_libre, st_adj


def _cas_exemplar():
    """`1087` -- la cible est une TUILE. Le seul terme DISCRIMINANT est l'ALLIE ADJACENT :
    `GetAdjacentUnits(target).RemoveAll(IsEnemy(u, caster))` doit rester NON VIDE.

    Le bras qui REFUSE met un ENNEMI a cote de la tuile (le `RemoveAll` le retire, il ne reste
    rien) ; celui qui ACCEPTE met un ALLIE a la MEME place. Un seul champ change : le camp.

    ⚠ LE VOISIN DOIT ETRE ADJACENT A LA TUILE CIBLE, pas au caster -- premiere version de ce
    substrat : le voisin etait pose en `B` (a cote du CASTER) et la cible en `LOIN`, donc les deux
    bras rendaient le MEME refus, la regle n'ayant aucun voisin a examiner. Le voisin est donc
    derive du board (`neighbours(tuile)`), et l'etape 0 verifie que ce voisinage n'est pas vide."""
    from probe_287r4r1_dynamic_target_rules import _board
    b = _board()
    tid = _tid(LOIN)
    vois = [n for n in b.neighbours(tid) if b.walkable(n)]
    cv = b.coord(vois[0])
    ennemi = [(CASTER, "tauShadowsun", 1, A[0], A[1], []),
              (ENNEMI, "necroWarden", 2, cv[0], cv[1], [])]
    allie = [(CASTER, "tauShadowsun", 1, A[0], A[1], []),
             (ALLIE, "tauCrisis", 1, cv[0], cv[1], [])]
    # TROISIEME bras : le SEUL voisin est le CASTER lui-meme. Le natif le RETIRE explicitement
    # (`units.Remove(caster)`, slot 6 d'`ICollection<T>`) AVANT le `RemoveAll(IsEnemy)`, qui ne
    # l'aurait pas retire (`IsEnemy(caster, caster)` est faux). Ce bras a ete trouve par la mesure
    # LIVE, en SOUS-REFUS -- aucune bascule ami/ennemi ne pouvait l'exhiber.
    seul_caster = [(CASTER, "tauShadowsun", 1, cv[0], cv[1], [])]
    return substrat(ennemi), substrat(allie), tid, substrat(seul_caster)


def _cas_alpha_warrior():
    """`1112` -- la cible est une TUILE, et la bascule est SPATIALE : dans / hors la bulle synapse
    d'une unite de l'EQUIPE du caster.

    Le porteur de l'aura est le caster lui-meme (`tyranWingedPrime` porte `UnitTrait.Synapse` au
    gameconfig) ; le trait passe ici par le canal MESURE `combatSnapshot.units[].traits`, donc
    l'ensemble effectif que rend `UnitExtensions$$HasTrait`, et non un kit qui pourrait bouger.
    `SynapseEffect$$GetCurrentRange` = `Direct(2)` -> une tuile a `d <= 2` est dedans."""
    u = [(CASTER, "tyranWingedPrime", 1, A[0], A[1], [UnitTrait.Synapse])]
    st = substrat(u)
    return st, _tid(B), _tid(LOIN)


BASCULES = []


def mesurer_bascule() -> list:
    """Rend [(aid, libelle, refus_attendu, obtenu_refus, obtenu_accepte)]."""
    out = []
    st_moved, st_libre, st_adj = _cas_sky_strike()
    aid = int(ActiveAbilityType.SkyStrike)
    out.append((aid, "1025 a bouge + NON adjacent -> CasterHasNotMoved",
                int(TR.CasterHasNotMoved), _regle(aid, st_moved), _regle(aid, st_libre)))
    out.append((aid, "1025 a bouge MAIS adjacent -> le court-circuit accepte",
                int(TR.CasterHasNotMoved), _regle(aid, st_moved), _regle(aid, st_adj)))

    aid = int(ActiveAbilityType.ExemplarOfTheKauyon)
    st_enn, st_all, tuile, st_seul = _cas_exemplar()
    out.append((aid, "1087 tuile libre : voisin ENNEMI vs voisin ALLIE",
                int(TR.TargetMatchesDynamicRule),
                _regle(aid, st_enn, CASTER, tuile), _regle(aid, st_all, CASTER, tuile)))
    out.append((aid, "1087 SEUL voisin = le CASTER (Remove) vs un ALLIE tiers",
                int(TR.TargetMatchesDynamicRule),
                _regle(aid, st_seul, CASTER, tuile), _regle(aid, st_all, CASTER, tuile)))

    aid = int(ActiveAbilityType.AlphaWarrior)
    st, dedans, dehors = _cas_alpha_warrior()
    out.append((aid, "1112 tuile HORS synapse vs DANS la synapse d'equipe",
                int(TR.TargetMatchesDynamicRule),
                _regle(aid, st, CASTER, dehors), _regle(aid, st, CASTER, dedans)))
    return out


def mesurer_tuile_sans_voisin() -> tuple:
    """`1025` bras `TargetHasFreeAdjacentTile` -- le SECOND code de refus, celui qu'une bascule a
    deux bras raterait. Il exige une cible dont AUCUNE tuile adjacente n'est libre : on entoure la
    cible d'unites. Rend (obtenu, attendu, nb_voisins_occupes)."""
    from probe_287r4r1_dynamic_target_rules import _board
    b = _board()
    tid = b.id_at(int(LOIN[0]), int(LOIN[1]))
    voisins = [n for n in b.neighbours(tid) if b.walkable(n)]
    u = [(CASTER, "adeptCelestine", 1, A[0], A[1], []),
         (CIBLE, "necroWarden", 2, LOIN[0], LOIN[1], [])]
    for i, n in enumerate(voisins):
        c = b.coord(n)
        u.append((100 + i, "necroWarden", 2, c[0], c[1], []))
    st = substrat(u)
    return _regle(int(ActiveAbilityType.SkyStrike), st), int(TR.TargetHasFreeAdjacentTile), len(voisins)


# ================================================================================================
# 2. MUTANTS -- en DELTA
# ================================================================================================

def mesurer_mutants() -> list:
    """Rend [(aid, libelle, a_morde, avant, apres)] -- `a_morde` = `avant == refus ET apres == 0`."""
    out = []
    st_moved, _libre, _adj = _cas_sky_strike()
    st_enn, _all, tuile, _seul = _cas_exemplar()
    st_aw, _dedans, dehors = _cas_alpha_warrior()
    cas = [(int(ActiveAbilityType.SkyStrike), "1025", st_moved, CIBLE, int(TR.CasterHasNotMoved)),
           (int(ActiveAbilityType.ExemplarOfTheKauyon), "1087", st_enn, tuile,
            int(TR.TargetMatchesDynamicRule)),
           (int(ActiveAbilityType.AlphaWarrior), "1112", st_aw, dehors,
            int(TR.TargetMatchesDynamicRule))]
    for aid, lib, st, tgt, refus in cas:
        avant = _regle(aid, st, CASTER, tgt)
        with desarme(aid):
            apres = _regle(aid, st, CASTER, tgt)
        out.append((aid, lib, avant == refus and apres == 0, avant, apres))
    return out


# ================================================================================================
# 3. LE CRAN SOUS L'ETAGE -- `SynapseEffect` comme `IAuraEffect`
# ================================================================================================

def mesurer_aura_synapse() -> dict:
    """`SynapseEffect` : `GetTrait` = `0x7e8 UnitTrait.Synapse`, et les TROIS slots de portee
    partagent un corps `Direct(2)` (quatre pointeurs de vtable consecutifs, cf. `aura.py`).

    L'invariant qui compte : la portee de Synapse ne depend PAS de `TurnsStarted`, alors que celle
    de Contagions, elle, en depend -- l'ajout ne doit pas avoir aplati la seconde."""
    syn = int(EffectType.Synapse_Effect)
    con = int(EffectType.ContagionsOfNurgle_ArmorReduction1)
    return {
        "synapse_est_aura": is_aura_effect(syn),
        "synapse_trait": aura_trait(syn),
        "synapse_trait_attendu": int(UnitTrait.Synapse),
        "synapse_max": aura_max_range(syn),
        "synapse_courante": [aura_current_range(syn, n) for n in (0, 1, 3, 5, 9)],
        "synapse_prochain": [aura_next_turn_range(syn, n) for n in (0, 2, 4)],
        "contagions_courante": [aura_current_range(con, n) for n in (0, 3, 5)],
        "non_aura": aura_current_range(int(EffectType.Markerlight), 3),
    }


# ================================================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r8 : les trois regles, offline")
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()

    print("[287r8] 0. GEOMETRIE DU SUBSTRAT (une bascule spatiale sur une tuile absente serait vraie"
          " par vacuite)")
    geo_ok = True
    for nom, c, existe, marchable in verifier_geometrie():
        print("  %-10s %-10s existe=%-5s marchable=%s" % (nom, c, existe, marchable))
        geo_ok = geo_ok and existe and marchable

    print("[287r8] 1. RECENSEMENT -- canal d'evaluation attendu")
    attendu = {int(ActiveAbilityType.SkyStrike): "surcharge",
               int(ActiveAbilityType.ExemplarOfTheKauyon): "table",
               int(ActiveAbilityType.AlphaWarrior): "surcharge"}
    canal_ok = True
    for aid, att in sorted(attendu.items()):
        got = evaluabilite(aid)
        print("  %-6d attendu=%-10s obtenu=%s" % (aid, att, got))
        canal_ok = canal_ok and got == att

    print("[287r8] 2. BASCULE -- chaque couple ne differe que par la grandeur LUE")
    basc = mesurer_bascule()
    basc_ok = True
    for aid, lib, refus, r, ok in basc:
        d = (r == refus and ok == 0)
        basc_ok = basc_ok and d
        print("  %-6d %-56s refuse=%-12s accepte=%-6s %s"
              % (aid, lib, hex(r), hex(ok), "DISCRIMINE" if d else "!! NE DISCRIMINE PAS"))
    got, att, nvois = mesurer_tuile_sans_voisin()
    second_ok = got == att
    print("  %-6d 1025 SECOND code de refus : cible ceinturee (%d voisins occupes) -> %s "
          "(attendu %s) %s" % (int(ActiveAbilityType.SkyStrike), nvois, hex(got), hex(att),
                               "OK" if second_ok else "!! FAUTE"))

    print("[287r8] 3. MUTANTS -- critere DELTA (avant == refus ET apres == 0)")
    mut = mesurer_mutants()
    mut_ok = all(m[2] for m in mut)
    for aid, lib, morde, av, ap_ in mut:
        print("  %-6d %-6s a_morde=%-5s avant=%-12s desarme=%s" % (aid, lib, morde, hex(av), hex(ap_)))
    print("  a_morde : %d / %d" % (sum(1 for m in mut if m[2]), len(mut)))

    print("[287r8] 4. LE CRAN SOUS L'ETAGE -- SynapseEffect comme IAuraEffect")
    au = mesurer_aura_synapse()
    aura_ok = (au["synapse_est_aura"] and au["synapse_trait"] == au["synapse_trait_attendu"]
               and au["synapse_max"] == 2 and set(au["synapse_courante"]) == {2}
               and set(au["synapse_prochain"]) == {2}
               and au["contagions_courante"] == [1, 2, 3] and au["non_aura"] is None)
    print("  synapse : aura=%s trait=%s (attendu %s) max=%s courante(TurnsStarted 0/1/3/5/9)=%s"
          % (au["synapse_est_aura"], au["synapse_trait"], au["synapse_trait_attendu"],
             au["synapse_max"], au["synapse_courante"]))
    print("  NON APLATI : contagions courante(0/3/5)=%s ; un EffectType non-aura rend %s"
          % (au["contagions_courante"], au["non_aura"]))

    if a.detail:
        print("[287r8] detail des substrats : caster=%d cible=%d allie=%d ennemi=%d ; A=%s B=%s LOIN=%s"
              % (CASTER, CIBLE, ALLIE, ENNEMI, A, B, LOIN))

    ok = geo_ok and canal_ok and basc_ok and second_ok and mut_ok and aura_ok
    print("[287r8] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
