"""#1024 -- `ShieldOfFaith` (mythique de `adeptExorcist`) : l'arbre DSL, mesure par mesure.

Ce probe ne valide pas un port (il n'y en a pas -- cf. `docs/rl/case-1024-mythiques-mow-shield-of-faith-on-my-position.md`) :
il etablit le GROUND TRUTH de l'ability, etage par etage, pour que le port futur ait de quoi se
confronter. Il exerce les trois etages que le decompile ecrit :

  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ShieldOfFaithAbility$$CreateTrigger`
      (On(PreAttack) & IsUnitOnTileWithEffect(Target, [EffectType.Fire]))
    | (On(Attack)    & WasCrit)
    & IsUnit(Attacker) & AreFriends(Owner, Attacker) & HasRarity(Attacker, Mythic)

  `...ShieldOfFaithAbility$$CreateBehaviour(abilityState, triggerType)`
      triggerType != Custom -> TriggerAbilityDelayed(Owner, <cette ability>, delai 3)
      triggerType == Custom -> If( IsAlive(Attacker)
                                   & AmountIsZero(CurrentShieldAmount(Attacker, 3)),
                                   CreateShield(Attacker,
                                       PercentageOf(StatAmount(Attacker, <stat 5>, <2>),
                                                    ConfigVar(0x96 = shieldPct)),
                                       <source>, TurnsFromRounds(1), null, true) )

Trois BRAS, et les deux derniers sont des CONTRE-EPREUVES qui doivent rendre ZERO bouclier :

  `--bras mythique`  : mythique montee + crit force  -> bouclier ATTENDU sur l'ATTAQUANT
  `--bras sans-mythique` : meme build, sans `--equip-mythic` -> AUCUN bouclier
                       (separe << c'est ShieldOfFaith >> de << un bouclier vient d'ailleurs >>)
  `--bras sans-crit` : mythique montee, `--crit 0,0`  -> AUCUN bouclier
                       (separe le gate `WasCrit` du simple fait d'attaquer)

Le regime est SEPARANT et le probe le VERIFIE avant de conclure : le bras positif exige un
bouclier NON NUL, faute de quoi il rend ROUGE au lieu d'un vert vide.

Usage (state-file ABSOLU, cf. runner.md) :
  python probe_1024_shield_of_faith_live.py --bras mythique --level 4
  python probe_1024_shield_of_faith_live.py --bras sans-mythique
  python probe_1024_shield_of_faith_live.py --bras sans-crit
Sortie ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import rl_duel as R  # noqa: E402

#: porteur mythique (MoW `lineup`) -- `units.lineup.adeptExorcist.mythicAbilities == ["ShieldOfFaith"]`.
PORTEUR = "adeptExorcist"
ABILITY = "ShieldOfFaith"
#: roster TEMOIN : deux unites du pool rank 17. `adeptRetributor` est l'ATTAQUANT (celui qui doit
#: recevoir le bouclier) ; le second n'est la que pour remplir le roster.
P_UNITS = "adeptRetributor,adeptCanoness"
A_UNITS = "tyranTyrantGuard,tyranParasite"
ATTAQUANT_VIS = "adeptRetributor"
CIBLE_VIS = "tyranTyrantGuard"
#: board 7x9 entierement Grass -- toute tuile (col<7, row<9) est posable, donc la geometrie est
#: PILOTEE (`--place`/`--a-place`), jamais subie.
BOARD = "MC1_67"
POS_ATTAQUANT = (3, 4)
POS_CIBLE = (3, 5)          # voisin hex de POS_ATTAQUANT -- verifie par `hexgeo` au demarrage


def _unwrap(x):
    return x["result"] if isinstance(x, dict) and "result" in x else x


def _shields_par_entite(cs: dict) -> dict:
    """`combatSnapshot.units[].shields` -> {entityId: [ {id, amount, remaining}, ... ]}.

    Canal : `IdunBattle.Entities.Components.ShieldComponent` (liste d'instances @+0x10), le SEUL
    ecrivain etant `CreateShieldOperation` (cf. `docs/rl/case-342-shield-lever.md`)."""
    out = {}
    for u in (cs.get("units") or []):
        out[u.get("entityId")] = u.get("shields") or []
    return out


def _hpmax_par_entite(cs: dict) -> dict:
    return {u.get("entityId"): u.get("healthMax") for u in (cs.get("units") or [])}


def main() -> int:
    ap = argparse.ArgumentParser(description="#1024 -- ShieldOfFaith, ground truth live")
    ap.add_argument("--bras", choices=["mythique", "sans-mythique", "sans-crit"],
                    default="mythique")
    ap.add_argument("--level", type=int, default=4, help="palier de la mythique (1..4)")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--palier-tronque", action="store_true",
                    help="CONTRE-EPREUVE du palier 2 : tronque les paliers a l'ENTIER avant de "
                         "les ecrire au BC. Le palier 2 de `shieldPct` vaut 32.5 au gameconfig, et "
                         "c'est le SEUL non entier des 11 mythiques ; le seed BC, lui, porte "
                         "39043 valeurs de variable dont 0 non entiere. Si le bouclier REVIENT "
                         "avec ce drapeau, la cause est bien la VALEUR ECRITE, pas le palier.")
    a = ap.parse_args()

    assert hexgeo.distance(POS_ATTAQUANT, POS_CIBLE) == 1, "geometrie de montage non adjacente"

    import catalog_inject  # noqa: E402
    import gameconfig  # noqa: E402

    cfg = gameconfig.ability(ABILITY) or {}
    paliers = (cfg.get("variables") or {}).get("shieldPct") or []
    print("=== ETAGE 0 : ce que le gameconfig dit ===")
    print("  ability   = %s (TriggeredAbilityType=%d)"
          % (ABILITY, catalog_inject.triggered_ability_id(ABILITY)))
    print("  shieldPct = %s  (rarity-flag: %s)"
          % (paliers, cfg.get("variablesAffectedByRarityBonus")))
    print("  porteurs  = %s" % (catalog_inject.mythic_carriers(ABILITY),))
    attendu_pct = paliers[a.level - 1] if 1 <= a.level <= len(paliers) else None
    print("  bras      = %s ; niveau demande = %d -> shieldPct attendu = %s"
          % (a.bras, a.level, attendu_pct))

    sf = a.state_file or str(Path(__file__).resolve().parents[2] / "logs"
                             / ("probe1024_sof_%s_l%d.json" % (a.bras, a.level)))
    crit = "0,0" if a.bras == "sans-crit" else "100,700"
    argv = ["build", "--seed", str(a.seed), "--board", a.board,
            "--p-units", P_UNITS, "--a-units", A_UNITS,
            "--p-mow", PORTEUR,
            "--crit", crit,
            "--place", "%s:%d,%d" % (ATTAQUANT_VIS, POS_ATTAQUANT[0], POS_ATTAQUANT[1]),
            "--a-place", "%s:%d,%d" % (CIBLE_VIS, POS_CIBLE[0], POS_CIBLE[1]),
            "--state-file", sf]
    if a.bras != "sans-mythique":
        argv[-2:-2] = ["--equip-mythic", "%s:%s:%d" % (PORTEUR, ABILITY, a.level)]

    if a.palier_tronque:
        # Substitution en FORME B : `equip_mythic` resout `synthesize_ability` par son nom de
        # MODULE a chaque appel, donc reaffecter l'attribut MORD (cf. CLAUDE.md, les trois formes).
        _orig = catalog_inject.synthesize_ability

        def _tronque(nom, *args, **kw):
            cfg = _orig(nom, *args, **kw)
            if nom != ABILITY:          # PORTEE MINIMALE : on ne touche qu'a l'ability mesuree
                return cfg
            for k, vals in (cfg.get("Variables") or {}).items():
                out = []
                for v in vals:
                    try:                # une variable peut etre une LISTE ("36,28,20") : intacte
                        out.append(str(int(float(v))))
                    except (TypeError, ValueError):
                        out.append(v)
                cfg["Variables"][k] = out
            return cfg

        catalog_inject.synthesize_ability = _tronque
        print("  [contre-epreuve] paliers tronques a l'entier : %s"
              % (_tronque(ABILITY).get("Variables"),))

    print()
    print("=== ETAGE 1 : build ===")
    if R.main(argv) != 0:
        print("  BUILD ECHOUE -- rien n'est conclu")
        return 2
    st = json.loads(Path(sf).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    print("  runnerId=%s  crit=%s  equip-mythic=%s"
          % (rid, crit, a.bras != "sans-mythique"))

    import rl_collect_batch as B  # noqa: E402
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(B._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    try:
        cs0 = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
        dv0 = rpc("decisionView", {"runnerId": rid}, 90) or {}
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
        att, cib = ids.get(ATTAQUANT_VIS), ids.get(CIBLE_VIS)
        hpmax = _hpmax_par_entite(cs0)
        sh0 = _shields_par_entite(cs0)
        print()
        print("=== ETAGE 2 : etat AVANT l'attaque ===")
        print("  attaquant u%s (%s) hpMax=%s  boucliers=%s"
              % (att, ATTAQUANT_VIS, hpmax.get(att), sh0.get(att)))
        print("  cible     u%s (%s) boucliers=%s" % (cib, CIBLE_VIS, sh0.get(cib)))
        if att is None or cib is None:
            print("  MONTAGE INCOMPLET (attaquant ou cible absent) -- rien n'est conclu")
            return 2
        if sh0.get(att):
            print("  MONTAGE NON SEPARANT : l'attaquant porte DEJA un bouclier avant l'attaque ;")
            print("  `AmountIsZero(CurrentShieldAmount(Attacker,3))` bloquerait la pose et le bras")
            print("  positif rendrait un vert VIDE. Rien n'est conclu.")
            return 2

        print()
        print("=== ETAGE 3 : l'attaque NORMALE ===")
        # #411-r2 : l'ability d'attaque normale est un id CONCRET, PAR UNITE -- jamais un defaut.
        # `_normal_ability_map` est le mirror deja porte de ce choix ; s'en remettre a
        # l'auto-resolution ferait jouer l'ACTIVE (ici `ArmoriumCherub`), en silence.
        na = R._normal_ability_map(dv0).get(att)
        print("  ability d'attaque normale de u%s : %s" % (att, na))
        if na is None:
            print("  ATTAQUE NORMALE NON RESOLUE -- rien n'est conclu")
            return 2
        act = rpc("applyAction", {"runnerId": rid,
                                  "action": {"kind": "ability", "casterId": att,
                                             "targetId": cib, "abilityType": na}}, 120) or {}
        blob = json.dumps(act)
        print("  mutated=%s eventCount=%s  occurrences didCrit=true : %d"
              % (act.get("mutated"), act.get("eventCount"), blob.count('"didCrit":true')))
        print("  ShieldOfFaith cite dans les events : %s ; CreateShield/AddOrUpdateShield : %s"
              % ("ShieldOfFaith" in blob, ("Shield" in blob)))

        cs1 = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
        sh1 = _shields_par_entite(cs1)
        print()
        print("=== ETAGE 4 : etat APRES ===")
        for eid, lst in sorted(sh1.items(), key=lambda kv: (kv[0] is None, kv[0])):
            if lst:
                print("  entite %-4s boucliers=%s" % (eid, lst))
        boucliers = sh1.get(att) or []

        print()
        print("=== VERDICT (%s) ===" % a.bras)
        if a.bras != "mythique":
            if boucliers:
                print("  CONTRE-EPREUVE ROUGE : un bouclier est apparu sur l'attaquant (%s)"
                      % boucliers)
                print("  -> le bras positif ne prouverait RIEN de ShieldOfFaith.")
                return 1
            print("  CONTRE-EPREUVE VERTE : aucun bouclier sur l'attaquant.")
            return 0
        if not boucliers:
            print("  AUCUN BOUCLIER : soit le trigger n'a pas passe, soit le behaviour n'a pas")
            print("  pose. Le probe ne tranche pas entre les deux -- il imprime ce qu'il a vu.")
            return 1
        amount = boucliers[0].get("amount")
        hm = hpmax.get(att)
        print("  BOUCLIER POSE : %s" % boucliers)
        if hm and attendu_pct is not None:
            attendu = hm * float(attendu_pct) / 100.0
            print("  hpMax(attaquant) = %s ; shieldPct[%d] = %s -> attendu ~= %.2f ; mesure = %s"
                  % (hm, a.level, attendu_pct, attendu, amount))
            print("  ecart = %+.2f (%.4f %% de l'attendu)"
                  % (amount - attendu, 100.0 * (amount - attendu) / attendu if attendu else 0.0))
        return 0
    finally:
        if not a.keep and rid is not None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
                print("  [runner %s dispose]" % rid)
            except Exception as exc:  # noqa: BLE001
                print("  [dispose echoue : %s]" % type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
