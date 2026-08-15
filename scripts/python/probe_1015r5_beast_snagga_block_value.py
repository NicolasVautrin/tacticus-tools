#!/usr/bin/env python
"""Probe #1015-r5 -- la VALEUR du block `BeastSnagga_ExtraBlock` (1081), confrontee LIVE.

CE QUE LA FICHE DISAIT, ET CE QUI A CHANGE
-------------------------------------------
`#1015-r1` avait confronte la POSE de 1081 (`decisionView.effects` AVEC = [1025, 1026, 1080, 1081],
SANS = [1025, 1026]) mais PAS sa VALEUR : le block est une entree de `GetMultiValueStat(7)`, qui
n'apparait ni dans le scalaire `GetStat(7/8)` ni dans `dmgMin`/`dmgMax`. La fiche `#1015-r5`
proposait un << montage a degat CALIBRE ou le block decide de la mort, lu par `WillBeKill` >>.

CE PROBE PREND LA MEME PORTE, MAIS UN CRAN PLUS BAS -- ET C'EST DIRECT.
`WillBeKill` n'est PAS l'observable le plus fin : c'est un BOOLEEN derive. Le mirror du getter
natif, lu dans `frida/hooks/game/damage-prediction.ts::computeWillBeKill`, l'ecrit noir sur blanc :

    if (CannotBeGuaranteedKilled) return false;
    m = (BlockScenarios != null && BlockScenarios.Count >= 1)
        ? BlockScenarios[0].Damage.HealthDamage.Min      <- `blockKillDmg`
        : DefaultScenario.Damage.HealthDamage.Min        <- `willKillDmg`
    return CurrentHealth <= m;

Les DEUX bornes qu'il compare sont DEJA publiees par le RPC `aiPredict`, avec en prime
`blockProbability` et `blockScenarioCount`. Calibrer un degat au PV pres pour faire basculer un
booleen reviendrait donc a mesurer par un seul bit ce que trois entiers disent directement -- et a
rendre le montage fragile a tout changement d'arrondi. On lit les entiers.

CE QUI EST CONFRONTE
--------------------
  1. `blockScenarioCount >= 1` SSI le defenseur porte le trait  -> la SOURCE de block existe ;
  2. `blockProbability` contre `beastSnaggaBlockChance` (traitVariables, LU) ;
  3. `willKillDmg - blockKillDmg` contre `PercentageOf(StatAmount(Owner, Health, Maximum),
     beastSnaggaDmgAsMaxHpPct)` -- c'est-a-dire l'amount que le port calcule ;
  4. le PORT (`BeastSnaggaExtraBlockEffect.create_effect_block_source_for_defense`) rend le MEME
     couple (chance, amount) sur les MEMES PV max.

TEMOIN NON DEGENERE : le bras SANS trait doit rendre `blockScenarioCount == 0`. Sans lui, un
`blockProbability` de 10 pourrait venir de n'importe quelle autre source de block du defenseur --
et `PsychicFortress_ExtraBlock` vaut AUSSI 10, donc le confond est reel, pas theorique.

MONTAGE. Le seul porteur du kit est `tauNpcFarsight` (npc, hors pool) -> le trait se GREFFE par
`--unit-stat "<vis>:Traits=[...]"`, greffe LEGITIME au sens de `case-92` SS5bis : l'arbre de
`BeastSnaggaAbility$$CreateBehaviour` pose `AddExtraBlockEffectToOwner` avec deux
`GetNumberConstant` et un `StatAmount(Owner, Health, Maximum)` -- il ne lit ni les stats ni les
traits d'un CASTER. MEME greffe que `probe_1015r1_beast_snagga.py`, dont ce probe est le pendant
sur l'axe BLOCK.

⚠ ICI LE PORTEUR DU TRAIT EST LE **DEFENSEUR** : `AddExtraBlockEffectToOwner` pose l'entree sur
`Owner`, et une source de block s'exerce quand son porteur est ATTAQUE. Le probe #1015-r1, lui,
greffait le trait sur l'ATTAQUANT (axe DEGAT). Confondre les deux rendrait un temoin vide.

ASCII only. Usage :
    python probe_1015r5_beast_snagga_block_value.py [--keep]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as R                                                      # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                  # noqa: E402
from engine.entities.effects.magnitude import trait_var                  # noqa: E402

BOARD = "MC1_67"
SEED = 777
TRAIT = UnitTrait.BeastSnagga.name
#: L'ATTAQUANT. Peu importe son kit : le block se lit sur le DEFENSEUR.
ATTAQUANT = "astraBullgryn"
#: LE PORTEUR DU BLOCK, cote DEFENSE. `adeptCanoness` est un HERO du pool, sans source de block
#: propre -- c'est ce qui rend `blockScenarioCount == 0` un temoin NON DEGENERE.
DEFENSEUR = "adeptCanoness"
TRAITS_DEFENSEUR = [UnitTrait.Hero.name]
EFFET_BLOCK = int(EffectType.BeastSnagga_ExtraBlock)                     # 0x439 = 1081
#: PV du defenseur balayes a l'etage 3 -- l'amount vaut 20 %% des PV MAX, donc baisser les PV
#: baisse l'amount jusqu'a passer SOUS le degat par coup et lever la saturation.
HP_BALAYAGE = (4000, 1500, 600, 200)


def _res(r):
    if isinstance(r, dict) and "result" in r:
        return r["result"]
    return r


def _build(sid, state_file: str, avec_trait: bool, hp_target: int = 0):
    traits = list(TRAITS_DEFENSEUR) + ([TRAIT] if avec_trait else [])
    args = ["build", "--seed", str(SEED), "--board", BOARD,
            "--p-units", ATTAQUANT, "--a-units", DEFENSEUR]
    if hp_target:
        # ⚠ `--hp-target`, PAS `--unit-stat <vis>:Health=<n>` : mesure (et meme lecon que
        # `probe_1015r1`), le second ECRIT bien `Health` dans `BC.Units[]` mais la normalisation
        # recalcule les PV en aval. Ici le levier est PORTANT : l'amount du block vaut
        # `20 %` des PV MAX, donc faire varier les PV fait varier l'amount -- c'est ce qui
        # DECOINCE l'etage 3 (cf. sa docstring).
        args += ["--hp-target", str(hp_target)]
    args += [
            "--unit-stat", "%s:Traits=%s" % (DEFENSEUR, str(traits).replace("'", '"')),
            # ⚠ LE BLOCK NATUREL DU DEFENSEUR DOIT PARTIR, ET C'EST UNE MESURE QUI L'IMPOSE.
            # Premiere passe sans cette ligne : `blockScenarioCount` valait **1** dans le bras
            # SANS trait et **2** dans le bras AVEC, et `blockProbability` rendait **36** -- la
            # chance de block PROPRE d'`adeptCanoness`. Le decodeur ne lit que `BlockScenarios[0]`
            # (cf. `computeWillBeKill`), donc les etages CHANCE et MONTANT mesuraient le mauvais
            # scenario. A `BlockChance=0`, le scenario 0 EST celui de `BeastSnagga`, et le bras
            # SANS retombe a 0 scenario -- ce qui rend le temoin lisible au lieu de decalé.
            "--unit-stat", "%s:BlockChance=0" % DEFENSEUR,
            # Le contact n'est pas espere : on met l'attaquant a portee du premier tour.
            "--unit-stat", "%s:Movement=12" % ATTAQUANT,
            "--state-file", state_file]
    return R.main(args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    chance_attendue = trait_var("BeastSnagga", "beastSnaggaBlockChance")
    pct_attendu = trait_var("BeastSnagga", "beastSnaggaDmgAsMaxHpPct")
    print("=== probe #1015-r5 -- VALEUR du block BeastSnagga_ExtraBlock (1081) ===")
    print("traitVariables LUES : beastSnaggaBlockChance=%s  beastSnaggaDmgAsMaxHpPct=%s"
          % (chance_attendue, pct_attendu))
    print("attaquant=%s  defenseur(porteur du block)=%s  board=%s  seed=%s\n"
          % (ATTAQUANT, DEFENSEUR, BOARD, SEED))

    sid = R._resolve_session()
    logs = PYDIR.parents[1] / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    bras, rc = {}, 0
    etats = []
    try:
        for nom, avec in (("AVEC", True), ("SANS", False)):
            sf = str(logs / ("probe1015r5-%s.json" % nom.lower()))
            etats.append(sf)
            _build(sid, sf, avec)
            st = R._load_state(sf) if hasattr(R, "_load_state") else None
            rid = (st or {}).get("runnerId")
            if rid is None:
                import json
                rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")

            def rpc(m, body=None, t=90):
                return _res(R._rpc(sid, m, [body] if body is not None else [], timeout=t))

            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150) or {}
            unites = {u.get("entityId") or u.get("id"): u for u in (dec.get("units") or [])}
            att = deff = None
            for uid, u in unites.items():
                vis = u.get("unitId") or u.get("visualId") or u.get("name")
                if vis == ATTAQUANT:
                    att = uid
                elif vis == DEFENSEUR:
                    deff = uid
            effets = {int(e.get("effectType")) for e in (dec.get("effects") or [])
                      if e.get("effectType") is not None
                      and (e.get("targetId") == deff or e.get("unitId") == deff)}
            pred = _res(R._rpc(sid, "aiPredict",
                               [{"runnerId": rid, "unitId": att, "targetId": deff}],
                               timeout=120)) or {}
            p = pred.get("pred") or {}
            bras[nom] = {"runner": rid, "att": att, "def": deff,
                         "block_pose": EFFET_BLOCK in effets,
                         "count": p.get("blockScenarioCount"),
                         "proba": p.get("blockProbability"),
                         "kill": p.get("willKillDmg"), "block_kill": p.get("blockKillDmg"),
                         "hp": p.get("hpBefore"), "err": pred.get("err")}
            b = bras[nom]
            print("[%s] runner=%-4s att=%s def=%s block_pose=%s"
                  % (nom, rid, att, deff, b["block_pose"]))
            print("       blockScenarioCount=%s blockProbability=%s willKillDmg=%s "
                  "blockKillDmg=%s hpBefore=%s err=%s"
                  % (b["count"], b["proba"], b["kill"], b["block_kill"], b["hp"], b["err"]))

        a, s = bras.get("AVEC"), bras.get("SANS")
        if not a or not s:
            print("\nNON MESURE : un bras manque.")
            return 1

        print("\n--- etage 1 : la SOURCE de block existe SSI le trait est la (temoin) ---")
        if a["count"] is None or s["count"] is None:
            print("NON MESURE : `blockScenarioCount` absent -- le decodeur n'a pas lu ce champ.")
            rc = 1
        elif int(a["count"]) == int(s["count"]) + 1:
            # Le critere est l'ECART, pas la valeur absolue : le trait AJOUTE une source. Ecrire
            # << AVEC >= 1 et SANS == 0 >> supposerait que le defenseur n'a aucun autre block, ce
            # qui est faux des qu'on change de porteur -- premiere passe mesuree : 2 / 1.
            print("OK  count AVEC=%s = SANS=%s + 1 : le trait AJOUTE exactement une source"
                  % (a["count"], s["count"]))
            if int(s["count"]) != 0:
                print("    (le defenseur garde %s source(s) propre(s) : les etages CHANCE et"
                      % s["count"])
                print("     MONTANT lisent `BlockScenarios[0]` et pourraient viser la mauvaise)")
                rc = 1
        else:
            print("ECART  count AVEC=%s SANS=%s (attendu SANS+1 / SANS)"
                  % (a["count"], s["count"]))
            rc = 1

        print("\n--- etage 2 : la CHANCE ---")
        if a["proba"] is None:
            print("NON MESURE : `blockProbability` absent.")
            rc = 1
        elif int(a["proba"]) == int(chance_attendue):
            print("OK  blockProbability=%s == beastSnaggaBlockChance=%s"
                  % (a["proba"], chance_attendue))
        else:
            print("ECART  blockProbability=%s != beastSnaggaBlockChance=%s"
                  % (a["proba"], chance_attendue))
            rc = 1

        print("\n--- etage 3 : le MONTANT, par BALAYAGE des PV du defenseur ---")
        # POURQUOI UN BALAYAGE. A PV pleins, `blockKillDmg` vaut **0** : l'amount (20 % des PV max)
        # depasse le degat de CHAQUE coup, donc le scenario de block les annule tous et la borne
        # basse sature -- l'ecart y bute sur le degat total au lieu de reveler l'amount. En
        # baissant les PV on baisse l'amount, jusqu'a passer SOUS le degat par coup : la saturation
        # cesse et `willKillDmg - blockKillDmg` devient une fonction LISIBLE de l'amount.
        # Un seul point de mesure aurait donc rendu << non decidable >> et fait croire a un
        # blocage ; c'est le BALAYAGE qui separe << sature >> de << faux >>.
        print("hp_target | willKillDmg | blockKillDmg | ecart | amount attendu (hp*%s/100)"
              % pct_attendu)
        lisible = 0
        for hp_t in HP_BALAYAGE:
            sf = str(logs / ("probe1015r5-hp%d.json" % hp_t))
            etats.append(sf)
            _build(sid, sf, True, hp_target=hp_t)
            import json as _json
            rid2 = _json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
            dec2 = _res(R._rpc(sid, "decisionView", [{"runnerId": rid2, "allAbilities": True}],
                               timeout=150)) or {}
            att2 = def2 = None
            for u in (dec2.get("units") or []):
                vis = u.get("unitId") or u.get("visualId") or u.get("name")
                uid = u.get("entityId") or u.get("id")
                if vis == ATTAQUANT:
                    att2 = uid
                elif vis == DEFENSEUR:
                    def2 = uid
            pr = (_res(R._rpc(sid, "aiPredict",
                              [{"runnerId": rid2, "unitId": att2, "targetId": def2}],
                              timeout=120)) or {}).get("pred") or {}
            wk, bk, hp = pr.get("willKillDmg"), pr.get("blockKillDmg"), pr.get("hpBefore")
            att_amt = (int(int(hp) * int(pct_attendu) / 100) if hp else None)
            ec = (int(wk) - int(bk)) if (wk is not None and bk is not None) else None
            sature = (bk == 0)
            print("%-9s | %-11s | %-12s | %-5s | %-6s %s"
                  % (hp_t, wk, bk, ec, att_amt, "(SATURE)" if sature else ""))
            if not sature and ec is not None and att_amt is not None:
                lisible += 1
                if ec % att_amt != 0:
                    print("   ECART : l'ecart %s n'est pas un multiple de l'amount %s"
                          % (ec, att_amt))
                    rc = 1
                else:
                    print("   OK : ecart = %d x amount -> le natif bloque %d coup(s) dans ce"
                          " scenario" % (ec // att_amt, ec // att_amt))
        if lisible == 0:
            print("NON DECIDABLE sur tout le balayage : `blockKillDmg` reste SATURE a 0.")
            print("Le MONTANT du block reste donc NON CONFRONTE -- la CHANCE (etage 2), elle,")
            print("l'est. C'est un RESULTAT partiel, ecrit comme tel, pas un vert.")
            rc = 1

        print("\n--- etage 4 : le PORT, sur les MEMES entrees ---")
        from engine.entities.effects.loki.hits import BeastSnaggaExtraBlockEffect
        eff = BeastSnaggaExtraBlockEffect(EFFET_BLOCK)
        for maxhp in (1000, 6525, 12047):
            src = eff.create_effect_block_source_for_defense(defender_max_health=maxhp)
            attendu = int(maxhp * int(pct_attendu) / 100)
            ok = src is not None and int(src.amount) == attendu \
                and int(src.chance) == int(chance_attendue)
            print("maxHP=%-6s -> port chance=%s amount=%s ; attendu chance=%s amount=%s  %s"
                  % (maxhp, src and src.chance, src and src.amount,
                     chance_attendue, attendu, "OK" if ok else "ECART"))
            if not ok:
                rc = 1
        # tri-etat : PV max non threades -> AUCUNE source (jamais un amount devine)
        if eff.create_effect_block_source_for_defense(defender_max_health=0) is not None:
            print("ECART : PV max non threades -> le port INVENTE une source de block")
            rc = 1
        else:
            print("OK  PV max non threades -> aucune source (tri-etat tenu)")
    finally:
        if not args.keep:
            for sf in etats:
                try:
                    R.main(["dispose", "--state-file", sf])
                except Exception:                       # noqa: BLE001 -- nettoyage best-effort
                    pass
            print("\n[dispose] %d runner(s)" % len(etats))
    print("\nrc = %d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
