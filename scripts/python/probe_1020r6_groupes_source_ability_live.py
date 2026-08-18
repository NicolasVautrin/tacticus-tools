"""#1020-r6 -- un groupe de coups ADDITIONNELS peut-il declencher un TRANSFERT de degat ?

## Ce que la fiche annoncait, et ce que le decompile en dit

`execute_additional_hits` ne threadait AUCUN `AbilityOrEffect` : le canal
`AbilityEntities+0x98` restait vide sur les coups d'un groupe, donc le gate `HasValue` de
`IdunBattle.Entities.Behaviours.TransferDamageBehaviour$$Execute` (#1020-r2) REFUSAIT le
transfert -- alors que le natif l'accepte. Divergence RESTRICTIVE.

LU, sur les DEUX voies natives de coups additionnels -- un groupe n'a JAMAIS d'`AbilityOrEffect`
propre, il HERITE de celui de son attaque :

  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
    (voie SANS profil, appelee inline par `Execute`) batit l'`AbilityEntities` des groupes en
    construisant DEUX `Nullable<AbilityOrEffect>` a partir du MEME `abilityOrEffect` recu de
    l'attaque parente, et les pose en `+0x60` (`CurrentAbility`) ET `+0x98`
    (`TriggeringAbility`) -- deux `Nullable$$.ctor` consecutifs sur le meme bloc de 0x18 octets ;
  * `Core.Services.OperationProcessor$$ExecuteAdditionalHitsWithDamageProfileType` (voie A
    PROFIL) RECOPIE son bloc d'options (0x18) et l'`AbilityEntities` (0x128) tels quels vers
    `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`, qui les
    repasse au slot `0x3c` sans les reconstruire.

## Le montage -- FIXTURE NOMMEE, empruntee et non recopiee

`probe_1020_savior_protocols_live.stage()` monte deja le triangle
`attaquant -> victime <- protecteur adjacent`, positions FORCEES. On le reutilise TEL QUEL en ne
changeant qu'une chose : l'ATTAQUANT devient `orksRuntherd`, dont le passif `SquigHound`
(`nrOfHits = 2`, `damageProfile = Physical`, bornes PREDEFINED `[minDmg, maxDmg]`, `range = 2`)
ajoute un GROUPE de coups additionnels APRES les coups d'arme. C'est le seul porteur du corpus qui
donne, dans UNE action, les deux regimes cote a cote : coups d'arme (canal DEJA threade) et coups
de groupe (canal qui manquait). Le contraste est donc INTERNE a la mesure.

## L'ORACLE, et pourquoi il ne peut pas se fitter

Le `Maybe(chance)` de `SaviorProtocolsAbility$$CreateBehaviour` est tire DANS le `CreateBehaviour`,
AVANT que `TransferDamageBehaviour$$Execute` n'evalue son gate `HasValue` -- le flux PRNG est donc
le MEME avec et sans le canal, seul le RESULTAT change. Trois canaux INDEPENDANTS sont lus :

  * `transferts_port` -- les appels REELS a `transfer_damage_operation`, comptes a la source ;
  * les PV du drone et de la victime, AVANT/APRES, des deux cotes ;
  * `mti` -- la position du MT en sortie, qui doit etre la MEME dans les deux bras du port
    (si elle differait, l'ecart de PV appartiendrait au FLUX, pas au canal).

## LA VENTILATION EST PAR (CIBLE, ATTAQUANT) -- et c'est LOAD-BEARING (#1020-r11)

Le flux d'UNE action ne contient pas que l'attaque : `SquigHoundSummonUnitAbility` fait
apparaitre une unite pendant cette action, et cette unite ATTAQUE (noeud
`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition` range dans les
`SpawnUnitOptions` du `Spawn`). Sommer les `Amount` par `Target_Id` SEUL compte donc son coup
comme un coup de l'attaque -- ce qui a fait ecrire, chiffrer et ouvrir un ecart de port
INEXISTANT. Tout ce que ce probe confronte au port passe par `_events_damage_ventile`, et ce
qui n'est PAS de l'attaquant est IMPRIME (`HORS ATTAQUANT`), jamais jete ni fondu.

Bras `SANS_CANAL` = le port d'AVANT ce correctif : `execute_additional_hits` recoit
`source_ability=None`. Il doit DIVERGER du natif la ou le port livre concorde. S'il ne diverge
pas, le montage n'exerce pas le canal et le probe le DIT (`REFUS`) plutot que de rendre un vert.

ASCII only. Usage :
  `python probe_1020r6_groupes_source_ability_live.py [--seed 777] [--board MC1_67]`
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from probe_1020_savior_protocols_live import (          # noqa: E402
    DRONE, VICTIME, MontageError, _events_damage, _events_damage_ventile, _hp, _r, _sid,
    stage)
from engine.entities.pathfinding.board import Board     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

#: L'attaquant : porteur du passif `SquigHound` -> UN groupe de coups additionnels
#: (`nrOfHits = 2`) APRES ses coups d'arme, dans la MEME action.
ATTAQUANT = "orksRuntherd"
#: `Loki_NormalAttack` -- repli si `abilityTargets` ne rend pas la ligne `kind == "normal"`.
NORMAL_ATTACK_FALLBACK = 69


def _ids(sid, rid, attaquant: str = ATTAQUANT):
    """Resout les trois entites par leur `visualId`, jamais par un ordre d'apparition.

    Version GENERALISEE de `probe_1020_savior_protocols_live._ids`, qui epingle `ultraTitus`."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        vis = (u.get("visualId") or "")
        if vis.startswith(attaquant):
            out["att"] = u.get("id")
        elif vis.startswith(VICTIME):
            out["victime"] = u.get("id")
        elif "Drone" in vis:
            out["drone"] = u.get("id")
    return out, dv


def _normal_attack_id(sid, rid, att) -> int:
    ab = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": att}, 90)
    for row in (ab.get("abilities") or []):
        if (row.get("kind") or "") == "normal":
            return int(row.get("abilityType") or NORMAL_ATTACK_FALLBACK)
    return NORMAL_ATTACK_FALLBACK


def mesure_native(sid, rid, ids, ab_id):
    """Joue l'attaque cote NATIF et rend l'etat AVANT/APRES + le flux ventile."""
    hp0, ob0 = _hp(sid, rid)
    dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    snap0 = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ids["att"], "targetId": ids["victime"],
        "abilityType": int(ab_id)}}, 120)
    hp1, _ = _hp(sid, rid)
    rng1 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    coups, transferts = _events_damage(res)
    return {"hp0": hp0, "hp1": hp1, "dv0": dv0, "ob0": ob0, "snap0": snap0, "rng0": rng0,
            "rng1": rng1, "res": res, "events": coups, "transferts": transferts,
            # #1020-r11 : la MEME donnee, ventilee par `(cible, ATTAQUANT)`. C'est elle qui fait
            # foi des qu'on compare a une operation de degat du port : le flux d'une action
            # contient aussi ce que frappent les unites SUMMONEES pendant cette action.
            "ventile": _events_damage_ventile(res),
            "ok": bool(res.get("ok")) and all(a.get("ok") for a in (res.get("actions") or []))}


def _coups_de(nat, uid, att_id) -> list:
    """Les `Amount` subis par `uid` et infliges par `att_id` -- l'ATTAQUE, rien d'autre."""
    return list((nat["ventile"].get(int(uid)) or {}).get(int(att_id)) or [])


def _hors_attaquant(nat, att_id) -> dict:
    """Ce que le flux porte et qui N'EST PAS de l'attaquant : `{(cible, attaquant): [Amount]}`.

    IMPRIME plutot que jete : sur ce montage c'est l'attaque de l'unite SUMMONEE par
    `SquigHoundSummonUnitAbility`, et c'est exactement ce qu'un total par cible confondait
    avec un coup de l'attaque."""
    return {(t, a): v for t, m in (nat["ventile"] or {}).items() for a, v in m.items()
            if a != int(att_id)}


def mesure_port(nat, ids, board, canal: bool = True):
    """Rejoue LA MEME attaque sur le MEME etat, avec le MEME etat MT.

    `canal=False` = LE CONTREFACTUEL, c'est-a-dire le port d'AVANT #1020-r6 :
    `execute_additional_hits` recoit `source_ability=None`. On ne touche NI la formule NI le
    pipeline NI le registre -- une seule ENTREE est substituee, a un seul endroit."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent
    from engine.runner.operations.damage import AttackDamageOperation
    import engine.runner.operations.additional_hits as AH
    import engine.runner.operations.damage_ops.normal as NRM
    import engine.runner.operations.damage_ops.ability as ABL
    import engine.runner.abilities.behaviours.transfer as TR

    st = load_state(nat["dv0"], nat["ob0"], nat["snap0"], board=board)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(nat["rng0"]["mt"]), nat["rng0"]["mti"]
    st.rng = rng

    def hp(uid):
        e = st.get_entity(int(uid))
        c = e.get_component(HealthComponent) if e is not None else None
        return None if c is None else c.hp

    vrai_tr = TR.transfer_damage_operation
    vus = []

    def compte(state, caster_id, orig, tgt, hit_index=None, attack_ability=None):
        # `attack_ability` (#1020-r2) = le 5e parametre natif. Le stub porte le contrat REEL,
        # sinon le probe mesurerait son propre echafaudage.
        out = vrai_tr(state, caster_id, orig, tgt, hit_index=hit_index,
                      attack_ability=attack_ability)
        vus.append({"orig": orig, "final": tgt, "hit_index": hit_index,
                    "attack_ability": attack_ability, "applique": out is not None})
        return out

    vrai_ah = AH.execute_additional_hits
    o_n, o_a = NRM.execute_additional_hits, ABL.execute_additional_hits

    def _sans_canal(*a, **kw):
        kw["source_ability"] = None
        return vrai_ah(*a, **kw)

    avant = {k: hp(v) for k, v in ids.items()}
    TR.transfer_damage_operation = compte
    if not canal:
        # Les deux facades importent en FORME B (`from ..additional_hits import ...` lie un NOM
        # dans CHAQUE module) : substituer le seul module source NE MORD PAS. On substitue donc
        # les trois liaisons, et on les restaure toutes.
        AH.execute_additional_hits = _sans_canal
        NRM.execute_additional_hits = _sans_canal
        ABL.execute_additional_hits = _sans_canal
    try:
        r = AttackDamageOperation.execute(st, int(ids["att"]), int(ids["victime"]))
    finally:
        TR.transfer_damage_operation = vrai_tr
        AH.execute_additional_hits = vrai_ah
        NRM.execute_additional_hits = o_n
        ABL.execute_additional_hits = o_a
    apres = {k: hp(v) for k, v in ids.items()}
    return {"avant": avant, "apres": apres, "attack": r, "transferts": vus,
            "mti": st.rng.mti,
            "ah_hits": int(((r or {}).get("additional_hits") or {}).get("hits") or 0)}


def _perdu(m):
    return {k: (None if m["avant"][k] is None or m["apres"][k] is None
                else int(m["avant"][k]) - int(m["apres"][k])) for k in m["avant"]}


def temoin_drone_loin(seed: int, board_id: str, dmg) -> dict:
    """TEMOIN -- le MEME montage, drone HORS adjacence (`IsAdjacent(Owner, Target)` ferme).

    POURQUOI IL EST OBLIGATOIRE ICI : le couple `orksRuntherd`/`SquigHound` porte un residu de
    reproduction CONNU et ETRANGER a ce canal (R6-b' : le 2e coup d'un groupe n'est pas reproduit
    sur toutes les seeds). Sans ce bras, un ecart de degat sur la VICTIME se lirait comme un defaut
    du transfert. Avec lui, on sait ce que le port doit deja au montage AVANT que le drone
    n'intervienne -- le drone est DEPLACE, pas retire : roster, stats et ordre d'apparition
    identiques."""
    sid = _sid()
    rid, sf = stage(seed, board_id, attaquant=ATTAQUANT, dmg_attaquant=dmg, drone_loin=True)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        ids, _dv = _ids(sid, rid)
        if not all(k in ids for k in ("att", "victime", "drone")):
            raise MontageError("temoin : entites introuvables : %s" % ids)
        nat = mesure_native(sid, rid, ids, _normal_attack_id(sid, rid, ids["att"]))
        if not nat["ok"]:
            raise MontageError("temoin : applyAction REFUSEE")
        port = mesure_port(nat, ids, board, canal=True)
        r0 = port["attack"] or {}
        return {"natif": {k: sum(_coups_de(nat, v, ids["att"])) for k, v in ids.items()},
                "port": _perdu(port),
                "transferts_natifs": len(nat["transferts"]),
                "transferts_port": sum(1 for t in port["transferts"] if t["applique"]),
                "hors_attaquant": _hors_attaquant(nat, ids["att"]),
                # LE COMPTE DE COUPS, des deux cotes : c'est lui qui separe << le port applique
                # moins par coup >> de << le port execute un coup de moins >>.
                "coups_natif": _coups_de(nat, ids["victime"], ids["att"]),
                "coups_port_arme": r0.get("per_hit"),
                "coups_port_groupe": (r0.get("additional_hits") or {}).get("per_hit")}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        Path(sf).unlink(missing_ok=True)


def run(seed: int = 777, board_id: str = "MC1_67", dmg: int | None = 900) -> int:
    sid = _sid()
    rid, sf = stage(seed, board_id, attaquant=ATTAQUANT, dmg_attaquant=dmg)
    rc = 0
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        ids, _dv = _ids(sid, rid)
        if not all(k in ids for k in ("att", "victime", "drone")):
            raise MontageError("entites introuvables : %s" % ids)
        ab_id = _normal_attack_id(sid, rid, ids["att"])
        nat = mesure_native(sid, rid, ids, ab_id)
        if not nat["ok"]:
            raise MontageError("applyAction REFUSEE : %s" % json.dumps(nat["res"])[:400])
        avec = mesure_port(nat, ids, board, canal=True)
        sans = mesure_port(nat, ids, board, canal=False)

        # LE DEGAT NATIF PAR ENTITE se lit dans le FLUX (`UnitDamaged`, tag `Amount`), jamais dans
        # un delta d'`observeBattle` : mesure du 2026-08-17, `hp0` et `hp1` sont IDENTIQUES sur ce
        # montage alors que le flux porte trois coups et trois pas `TransferDamage` -- le RPC ne
        # republie pas les PV au grain ou on les attendait. Le flux, lui, est le canal que le natif
        # emet lui-meme.
        # #1020-r11 : VENTILE PAR ATTAQUANT. Le total par cible seule additionnait l'attaque de
        # l'unite SUMMONEE (cf. `_events_damage_ventile`) et faisait accuser le port d'un coup
        # manquant qu'il n'a jamais eu a executer.
        n_perdu = {k: sum(_coups_de(nat, v, ids["att"])) for k, v in ids.items()}
        n_hors = _hors_attaquant(nat, ids["att"])
        n_mti = (nat.get("rng1") or {}).get("mti")
        print("== #1020-r6 %s -> %s (protege par %s)" % (ATTAQUANT, VICTIME, DRONE))
        print("   HORS ATTAQUANT (cible, attaquant) -> montants = %s"
              % {str(k): v for k, v in n_hors.items()})
        print("   coups de GROUPE executes par le port = %d (0 => le montage n'exerce PAS le "
              "canal)" % avec["ah_hits"])
        print("   NATIF        amounts=%s transferts(step 35)=%d mti=%s"
              % (n_perdu, len(nat["transferts"]), n_mti))
        print("   PORT AVEC    perdu=%s transferts=%d appliques=%d mti=%s"
              % (_perdu(avec), len(avec["transferts"]),
                 sum(1 for t in avec["transferts"] if t["applique"]), avec["mti"]))
        print("   PORT SANS    perdu=%s transferts=%d appliques=%d mti=%s"
              % (_perdu(sans), len(sans["transferts"]),
                 sum(1 for t in sans["transferts"] if t["applique"]), sans["mti"]))
        print("   attack_ability vus AVEC = %s"
              % sorted({str(t["attack_ability"]) for t in avec["transferts"]}))
        print("   attack_ability vus SANS = %s"
              % sorted({str(t["attack_ability"]) for t in sans["transferts"]}))
        # DECOMPOSITION PAR COUP -- jamais un total. Un ecart de somme ne separe pas << un coup
        # manquant >> de << tous les coups un peu bas >>, et c'est exactement ce que les deux
        # canaux ci-dessous tranchent.
        print("   [par coup] NATIF victime=%s drone=%s"
              % (_coups_de(nat, ids["victime"], ids["att"]),
                 _coups_de(nat, ids["drone"], ids["att"])))
        for nom, m in (("AVEC", avec), ("SANS", sans)):
            r0 = m["attack"] or {}
            ah = (r0.get("additional_hits") or {})
            print("   [par coup] PORT %s arme=%s groupe=%s | transferts=%s"
                  % (nom, r0.get("per_hit"), ah.get("per_hit"),
                     [(t["hit_index"], t["applique"]) for t in m["transferts"]]))

        if avec["ah_hits"] <= 0:
            print("REFUS : aucun coup de groupe execute -- ce montage ne dit RIEN du canal.")
            return 2
        a_avec = sum(1 for t in avec["transferts"] if t["applique"])
        a_sans = sum(1 for t in sans["transferts"] if t["applique"])
        if a_avec == a_sans and _perdu(avec) == _perdu(sans):
            print("REFUS : les DEUX bras donnent le MEME resultat -- le montage ne discrimine "
                  "rien (aucun coup de groupe n'a tire un `Maybe` gagnant ?). Rejouer avec une "
                  "autre seed.")
            return 2
        print("DISCRIMINANT : transferts APPLIQUES AVEC=%d SANS=%d -- le canal MORD."
              % (a_avec, a_sans))
        # ⚠ LE FLUX N'EST PAS LE MEME DANS LES DEUX BRAS, ET C'EST ATTENDU :
        # `IdunBattle.Operations.TransferDamageOperation$$GetDamage` CONSOMME un tirage par
        # transfert REELLEMENT applique (cf. `triggers/loki/savior_protocols.py`). Un bras qui en
        # applique un de moins consomme donc un tirage de moins -- ce n'est pas un artefact, c'est
        # la signature meme du canal. Le `mti` est donc IMPRIME (contexte), jamais un verdict :
        # il est en plus pollue par le residu R6-b' du montage, que le TEMOIN ci-dessous chiffre.
        print("   [contexte] mti natif=%s AVEC=%s SANS=%s" % (n_mti, avec["mti"], sans["mti"]))
        # LES DEUX GRANDEURS QUE CE CANAL COMMANDE, et elles seules :
        #   (1) le NOMBRE de transferts appliques -- le port doit egaler le compte de pas
        #       `TransferDamage` (step 35) que le natif emet ;
        #   (2) le degat encaisse par le DRONE -- c'est-a-dire ce qui a ete DEPLACE.
        # Le degat de la VICTIME, lui, porte AUSSI le residu de reproduction du montage : il est
        # confronte au TEMOIN, pas au natif.
        nb_natif = len(nat["transferts"])
        if a_avec != nb_natif:
            print("!! PORT AVEC applique %d transfert(s), le natif en emet %d (step 35)"
                  % (a_avec, nb_natif))
            rc |= 1
        if a_sans == nb_natif:
            print("!! PORT SANS applique deja le compte NATIF -- ce montage n'etablit pas que le "
                  "canal etait necessaire.")
            rc |= 1
        pa, ps = _perdu(avec), _perdu(sans)
        if n_perdu.get("drone") and pa.get("drone") != n_perdu.get("drone"):
            print("!! DEPLACE : port AVEC=%s natif=%s" % (pa.get("drone"), n_perdu.get("drone")))
            rc |= 1
        if ps.get("drone") == n_perdu.get("drone"):
            print("!! DEPLACE : le port SANS deplace deja autant que le natif -- pas discriminant.")
            rc |= 1

        # TEMOIN : ce que le port doit deja au montage quand le drone est HORS d'adjacence.
        tem = temoin_drone_loin(seed, board_id, dmg)
        ecart_temoin = (tem["natif"].get("victime") or 0) - (tem["port"].get("victime") or 0)
        print("   TEMOIN drone LOIN : natif=%s port=%s (transferts natif=%d port=%d) -> ecart "
              "victime ETRANGER au canal = %d"
              % (tem["natif"], tem["port"], tem["transferts_natifs"], tem["transferts_port"],
                 ecart_temoin))
        print("   TEMOIN [par coup] natif=%s | port arme=%s groupe=%s"
              % (tem["coups_natif"], tem["coups_port_arme"], tem["coups_port_groupe"]))
        if tem["transferts_natifs"] or tem["transferts_port"]:
            print("!! TEMOIN INVALIDE : le drone hors adjacence transfere quand meme "
                  "(natif=%d port=%d)" % (tem["transferts_natifs"], tem["transferts_port"]))
            rc |= 1
        # Le temoin est le bras SANS consommateur : il garde que la lecture du pending relu est
        # STRICTEMENT NO-OP quand rien ne le consomme (`kept == demande` a l'identique).
        t_port = list(tem["coups_port_arme"] or []) + list(tem["coups_port_groupe"] or [])
        if t_port != list(tem["coups_natif"] or []):
            print("!! TEMOIN PAR COUP : natif=%s port=%s" % (tem["coups_natif"], t_port))
            rc |= 1
        # #1020-r11 -- FERME (2026-08-18). Ce bloc ANNONCAIT << des que le drone est adjacent, le
        # natif execute UN COUP DE PLUS que le port >>. C'etait un artefact de VENTILATION : le
        # total etait pris par `Target_Id` SEUL, donc il additionnait aux coups de l'ATTAQUE ceux
        # d'une AUTRE unite -- celle que
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility` fait
        # apparaitre pendant l'action, et qui attaque toute seule (`CreateBehaviour` range un
        # `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition` dans les
        # `SpawnUnitOptions` du `Spawn`). Ventile par ATTAQUANT (`_events_damage_ventile`),
        # l'attaque rend le MEME compte de coups et le MEME total des deux cotes : les deux
        # controles ci-dessous sont donc des VERDICTS, plus un commentaire.
        ecart_victime = (n_perdu.get("victime") or 0) - (pa.get("victime") or 0)
        n_coups = len(_coups_de(nat, ids["victime"], ids["att"]))
        r0 = avec["attack"] or {}
        p_coups = len(r0.get("per_hit") or []) + len(
            (r0.get("additional_hits") or {}).get("per_hit") or [])
        if n_coups != p_coups:
            print("!! COUPS : le natif en execute %d sur la victime, le port %d (hors attaquant : "
                  "%s)" % (n_coups, p_coups, {str(k): v for k, v in n_hors.items()}))
            rc |= 1
        # #1020-r11 -- LE VERDICT COUP PAR COUP, et pas seulement la somme. Le tag `Amount` du
        # natif est le pending RELU (`ApplyDamageOperation$$Execute` : `GetValueOrDefault` APRES
        # `On(0x39)`), donc un coup TRANSFERE y vaut 0. Un port qui rapporterait le DEMANDE
        # tomberait ici tout en gardant la MEME somme et le MEME etat -- exactement le genre
        # d'ecart qu'aucun test d'ETAT ne voit.
        p_liste = list(r0.get("per_hit") or []) + list(
            (r0.get("additional_hits") or {}).get("per_hit") or [])
        n_liste = _coups_de(nat, ids["victime"], ids["att"])
        if p_liste != n_liste:
            print("!! PAR COUP : natif=%s port=%s" % (n_liste, p_liste))
            rc |= 1
        if ecart_victime:
            print("!! VICTIME : natif=%d port=%d (ecart %d) -- ventile par ATTAQUANT, donc "
                  "l'ATTAQUE et rien d'autre (temoin drone LOIN : ecart %d)."
                  % (n_perdu.get("victime") or 0, pa.get("victime") or 0, ecart_victime,
                     ecart_temoin))
            rc |= 1
        print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL rc=%d" % rc))
        return rc
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--dmg", type=int, default=900,
                    help="borne le degat de l'attaquant pour que le drone SURVIVE a la serie")
    a = ap.parse_args()
    return run(a.seed, a.board, a.dmg)


if __name__ == "__main__":
    raise SystemExit(main())
