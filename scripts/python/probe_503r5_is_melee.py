"""#503-r5 -- `is_melee` de la triggered `1237` : le port ecrit `None`, le natif dit-il MELEE ?

QUESTION BINAIRE, POSEE AVANT LA METHODE. Le coup differe de `1141 OverwhelmingWrath` (phase 2,
`TriggeredAbilityType` 1237) est-il de nature **MELEE** pour les gates defensifs du jeu, ou de
nature INDETERMINEE (ni melee ni ranged) ?

CE QUE LE PORT ECRIT, ET POURQUOI. `overwhelming_wrath_attack_tree()` passe `is_melee=None`, et
c'est une LECTURE : les CINQ surcharges de
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ont ete decompilees et **aucune ne
porte de bit melee/ranged**. Ecrire `True` -- ce que le porteur (Azkor, melee) et le selecteur
`AdjacentEnemies` invitent a faire -- serait une DEDUCTION. Cote port, `None` fait TAIRE les DEUX
familles de gates (`is_melee_attack` / `is_ranged_attack`, mirror de
`BattleQuery$$IsMeleeAttack` / `$$IsRangedAttack`, qui ne rendent VRAI que si la nature est
PROUVEE).

POURQUOI CE MONTAGE-CI, ET PAS CELUI DE LA FICHE. La fiche #503-r1 annoncait « une cible portant un
reducteur gate RANGED » -- montage SANS PORTEUR : un balayage des
`create_effect_damage_malus_for_defense` du port rend **0** implementeur gate `IsRangedAttack`
qu'on puisse poser sur une cible de ce scenario. Le montage joue ici est l'AUTRE face du meme axe,
et il a un porteur immediat :

    on GREFFE le trait `Terrifying` sur `orksNob` (u81, la 1re cible du tir).

`Terrifying` derive `TerrifyingAbility`, qui pose `78 Terrifying_ExtraDefense` sur son porteur ;
cet effet est PORTE et son unique gate est `IsMeleeAttack`
(`IdunBattle.Entities.Effects.Terrifying_ExtraDefense_Effect$$CreateDamageModifier`), pour
`-globalValues.terrifyingBonus` % du degat MELEE recu. Le discriminant est donc DIRECT et ne
demande AUCUNE modification du port :

    natif traite `1237` en MELEE     ->  u81 encaisse MOINS que le port   (natif < port)
    natif ne le prouve NI l'un NI l'autre ->  u81 reste BIT-EXACT          (natif == port)

TEMOIN DE CONTROLE : `orksRuntherd` (u83) NE recoit PAS la greffe. Son verdict doit rester celui
de la tranche precedente -- sans lui, un ecart sur u81 ne se distinguerait pas d'un montage qui
aurait bouge autre chose.

Le montage (board `MC1_67`, seed 777, unites, placements, deux `endturn` NUS) est celui de
`probe_503r1_overwhelming_wrath_phase2.measure`, INSTRUMENTE par son point d'extension
`extra_args` : on ne le re-invente pas.

    python probe_503r5_is_melee.py [--state-file <chemin ABSOLU>] [--trait Terrifying]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import probe_503r1_overwhelming_wrath_phase2 as P

#: La cible GREFFEE (1re frappee, celle qui etait BIT-EXACTE avant greffe) et le TEMOIN.
CIBLE_GREFFEE = "orksNob"
TEMOIN = "orksRuntherd"
#: Le trait porteur du gate. `Terrifying` -> `TerrifyingAbility` -> effet 78, gate `IsMeleeAttack`.
TRAIT = "Terrifying"
TERRIFYING_EXTRA_DEFENSE = 78          # EffectType.Terrifying_ExtraDefense


def monter_seed(nom: str, trait: str) -> Path:
    """Ecrit le seed BC greffe sous `logs/` (SORTIE -> jamais `data/`, #349)."""
    import catalog_inject as CI
    out = P.LOGS / ("%s-seed.json" % nom)
    p, rapports = CI.write_trait_seed_bc(out, ["%s:%s" % (CIBLE_GREFFEE, trait)])
    print("[503-r5] greffe : %s" % json.dumps(rapports, ensure_ascii=True))
    return p


def mesurer(sid: int, nom: str, trait: str) -> dict:
    seed_bc = monter_seed(nom, trait)
    m, dispose = P.measure(sid, state_name=nom, extra_args=["--seed-bc", str(seed_bc)])
    try:
        return dict(m)
    finally:
        dispose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--trait", default=TRAIT)
    a = ap.parse_args()
    sid = P._session()
    nom = Path(a.state_file).stem if a.state_file else "probe_503r5_is_melee"
    m = mesurer(sid, nom, a.trait)
    rc = 0

    d_off = P._hp_delta(*m["off_hp"])
    d_live = P._hp_delta(*m["live_hp"])
    dmg_off = {k: v[0] - v[1] for k, v in d_off.items()}
    dmg_live = {k: v[0] - v[1] for k, v in d_live.items()}
    print("[503-r5] caster=u%s cible du cast=u%s" % (m["caster"], m["target"]))
    print("[503-r5] degat par cible : port %s | natif %s"
          % (json.dumps(dmg_off), json.dumps(dmg_live)))
    print("[503-r5] effets portes AVANT le tir (natif) : %s"
          % json.dumps(m["live_foot"][0], sort_keys=True))

    porteurs = [u for u, e in (m["live_foot"][0] or {}).items()
                if TERRIFYING_EXTRA_DEFENSE in e]
    print("[503-r5] porteurs de `Terrifying_ExtraDefense` (78) : %s" % porteurs)
    if not dmg_live:
        print("ECHEC : aucun degat natif -- regime DEGENERE, rien n'est discriminant")
        return 1
    cibles = sorted(dmg_live)
    greffee = [u for u in cibles if u in porteurs and u != m["caster"]]
    if not greffee:
        print("NON MONTE : aucune CIBLE frappee ne porte l'effet 78 -- la greffe n'a pas pris, "
              "ou la cible greffee n'est pas dans l'ensemble frappe. Ne RIEN conclure.")
        return 1

    for k in cibles:
        role = "GREFFEE" if k in greffee else "temoin "
        po, na = dmg_off.get(k, 0), dmg_live[k]
        print("    u%-4d %s port %-8d natif %-8d  %s"
              % (k, role, po, na, "BIT-EXACT" if po == na else "ECART %d" % (po - na)))

    g = greffee[0]
    po, na = dmg_off.get(g, 0), dmg_live[g]
    # LE VERDICT SE LIT CONTRE CE QUE L'ARBRE PORTE VRAIMENT, jamais contre une valeur en dur :
    # sans cette lecture, ce probe imprimerait « `None` CONFIRME » au moment meme ou le port vient
    # de passer a `True` -- il l'a fait, et c'est ce qui a impose ce cran.
    from engine.runner.operations.triggers.loki.overwhelming_wrath_attack import (
        overwhelming_wrath_attack_tree)
    ecrit = getattr(overwhelming_wrath_attack_tree(), "is_melee", "<illisible>")
    print("\nVERDICT #503-r5 -- l'arbre du port porte `is_melee=%r`" % (ecrit,))
    if po == na:
        print("    CONFIRME. Le porteur greffe encaisse EXACTEMENT ce que le port calcule avec")
        print("    cette valeur-la, et le TEMOIN non greffe n'a pas bouge : le gate")
        print("    `IsMeleeAttack` de `Terrifying_ExtraDefense` tombe du MEME cote des deux")
        print("    cotes. Remettre `None` ici ferait rougir ce probe de %d PV." % 2629)
    else:
        print("    REFUTE. Le natif retranche %d PV que le port ne retranche pas ;" % (po - na))
        print("    l'unique gate de `Terrifying_ExtraDefense` est `IsMeleeAttack`, donc le natif")
        print("    ne tient PAS ce coup pour ce que l'arbre en dit.")
        rc = 1
    temoins = [u for u in cibles if u not in greffee]
    for t in temoins:
        if dmg_off.get(t, 0) != dmg_live[t]:
            print("    ⚠ le TEMOIN u%d a bouge lui aussi (%d vs %d) : la greffe a deplace autre "
                  "chose, le verdict ci-dessus n'est PAS attribuable au seul gate."
                  % (t, dmg_off.get(t, 0), dmg_live[t]))
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
