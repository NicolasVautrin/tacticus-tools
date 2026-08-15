"""probe #419-r1-tr14-r5-r2-r1-r2-r1-r1 -- `get_range` desarmait `only_adjacent` sur une valeur NON LUE.

QUESTION BINAIRE
    Le natif DESARME-t-il son gate d'adjacence quand la portee NUMERIQUE n'est pas resoluble, ou
    l'evalue-t-il quand meme ? Et si c'est la seconde reponse : combien de couples
    (jeu d'options, unite) le port relachait-il, et sur combien d'abilities ?

CE QUE DIT LE DECOMPILE (verite ; le live ne fait que confirmer)

  `IdunBattle.Core.Services.TargetingQuery$$GetRange(caster, casterTiles, options)` -- les trois
  seules ecritures de `onlyAdjacent` (`cVar2` du decompile), dans l'ordre :

      onlyAdjacent = RangedBoolExtensions.IsTrue(options.Range.OnlyAdjacent, caster);   # AVANT tout
      ... v = <arme> ; v = OverrideRange.GetValueOrDefault(v) ; if (Func) v = Func(caster) ...
      if (HasEffect(caster, 0x529 ForcedInMelee))            { v = Math.Min(1, v); onlyAdjacent = 1; }
      if (IsTrue(options.ForceMeleeTarget, caster)
          && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
                                                            { v = Math.Min(1, v); onlyAdjacent = 1; }
      return new Range(Math.Min(v, cap ?? int.MaxValue), onlyAdjacent, options.Range.UseWholeBoard);

  **`onlyAdjacent` ne lit JAMAIS la valeur.** Il est pose avant toute resolution d'arme, et les deux
  seules ecritures suivantes le FORCENT a vrai sous des conditions qui ne lisent pas `v` non plus.
  Corollaire LU : les deux `Math.Min(1, v)` vivent dans le MEME bloc que `onlyAdjacent = 1`, donc
  une valeur clampee n'est jamais consommee (cf. ci-dessous) -- clamper un `None` est sans effet.

  La struct de retour fait TROIS champs, et c'est `GetTilesInRange` qui l'etablit definitivement
  (`if ((int)range < 0)`, `if (range._5_1_ == 0)`, `if (range._4_1_ == 0)`) :

      Range = { int Value @+0x00 ; bool OnlyAdjacent @+0x04 ; bool UseWholeBoard @+0x05 }

  Ce qui recoupe le court-circuit `UseWholeBoard` de `GetRange`, qui rend le litteral
  `0x10000000001` = { Value = 1, OnlyAdjacent = false, UseWholeBoard = true }.

  Le CONSOMMATEUR, `TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments), volet portee :

      if (!ignoreRangeChecks) {
          if (range.OnlyAdjacent) {                                  # range._4_1_
              if (!battleQuery.AreEntitiesAdjacent(casterTiles, target)) return TargetIsInRange;
          } else if (!options.Range.UseWholeBoard) {
              d = movementQuery.GetDistance(casterTiles, target);    # (int)range lu ICI SEULEMENT
              ...
          }
      }

  **La branche d'adjacence ne lit pas `Value`, et elle est testee EN PREMIER.** Le natif evalue donc
  bien le gate d'adjacence quel que soit l'etat de la portee numerique : la question binaire est
  tranchee, et dans le sens qui accuse le port.

LE CRITERE DISCRIMINANT, ENONCE AVANT LA MESURE
    Caster SANS AUCUNE ARME au gameconfig (`unit_weapon_range` -> None) donc NON `IsRanged`, jeu
    d'options a `only_adjacent = IfNotRangedCaster` (-> vrai), cible ENNEMIE a d >= 2 valide sur tous
    les autres axes :
        natif       REFUSE, et NOMME `TargetIsInRange` (0x8000000)
        port AVANT  ne pose AUCUN refus de portee (`get_range` rendait None)
        port APRES  REFUSE, et NOMME `TargetIsInRange`
    CE QUI M'AURAIT FAIT CONCLURE L'INVERSE : une ecriture de `onlyAdjacent` derivee de `v` dans
    `GetRange`, ou une lecture de `(int)range` dans la branche `OnlyAdjacent` du consommateur. Ni
    l'une ni l'autre n'existe -- verifie sur le decompile des deux fonctions.

CE QUE CE PROBE MESURE (offline, sans runner)
    Etape 1 -- le RAYON DE SOUFFLE, couple par couple : pour chaque jeu de `TargetingOptions` du port
      (registre `ABILITY_CLASSES`, `TARGETING_OPTIONS_UNPORTED`, et les 18 jeux d'attaque normale) x
      chaque unite du catalogue gameconfig, l'etat du gate AVANT et APRES.
    Etape 2 -- la CONTRE-EPREUVE de non-regression : les couples a portee OBSERVABLE doivent etre
      inchanges, bit a bit (le correctif ne doit rien deplacer la ou la valeur etait connue).
    Etape 3 -- l'etage JUMEAU `GetTilesInRange` (`engine.services.ability_range`) NE DOIT PAS etre
      aligne : il lit `Value` AVANT `OnlyAdjacent` (`(int)range < 0`, `== 0`), donc son `None` sur
      une portee non observable est CORRECT. Ce cran garde qu'on ne l'a pas "corrige" par symetrie.

VERDICT
    rc 0 si (a) le rayon de souffle est NON VIDE (sinon le correctif ne deplace rien et la mesure ne
    prouve rien), (b) aucun couple a portee observable n'a bouge, (c) l'etage jumeau rend toujours
    None sur une portee non observable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                   # noqa: E402

from engine.runner.abilities.handler import ABILITY_CLASSES               # noqa: E402
from engine.runner.abilities.targeting import (                           # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
    RANGED_BOOL_IF_RANGED_CASTER, TARGETING_OPTIONS_UNPORTED, unit_weapon_range)


def _catalogue() -> list:
    """Les `visualId` du catalogue gameconfig, tries. Substrat = celui que lit `unit_weapon_range`.

    ATTENTION : `GC.all_unit_ids()` rend un DICT `{kind: [ids]}` (3 cles `lineup`/`npc`/`summons`),
    pas une liste d'ids -- l'aplatir, sans quoi le balayage porte sur TROIS pseudo-unites et rend un
    chiffre qui a l'air d'une mesure."""
    idx = GC.all_unit_ids()
    ids = sorted({u for kind in ("lineup", "npc", "summons") for u in (idx.get(kind) or [])})
    if len(ids) < 100:
        raise RuntimeError("catalogue a %d entrees -- substrat SUSPECT, pas une mesure" % len(ids))
    return ids


def _is_ranged(vis: str) -> bool:
    """`UnitExtensions$$IsRanged` cote KIT : le trait `Ranged` (0xb) n'est porte par aucune unite
    (constat #161), donc le predicat se reduit a « possede une arme a `Range` »."""
    return any(w.get("Range") for w in ((GC.unit(vis) or {}).get("weapons") or []))


def _ranged_bool(value: int, vis: str) -> bool:
    """`RangedBoolExtensions$$IsTrue(RangedBool, unit)`, resolu sur le KIT (pas d'etat de bataille)."""
    v = int(value)
    if v == RANGED_BOOL_TRUE:
        return True
    if v == RANGED_BOOL_FALSE:
        return False
    if v == RANGED_BOOL_IF_RANGED_CASTER:
        return _is_ranged(vis)
    return not _is_ranged(vis)                       # IfNotRangedCaster


def _options_sources() -> list:
    """Les TROIS sources de `TargetingOptions` du port, chacune etiquetee par son origine."""
    out = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is not None:
            out.append(("registre", int(aid), opts))
    for aid, opts in sorted(TARGETING_OPTIONS_UNPORTED.items()):
        out.append(("unported", int(aid), opts))
    for t, opts in sorted(NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE.items()):
        out.append(("attaque-normale", int(t), opts))
    return out


def _gate_state(opts, vis: str) -> dict:
    """L'etat des DEUX gates de portee pour ce couple, AVANT et APRES le correctif.

    Modele du calcul, mirror de `get_range` -- **hors clamps de melee**, qui dependent de l'etat de
    bataille (`HasEffect(0x529)`, `ShouldApplyRangedInMelee`) et ne peuvent qu'ELARGIR le rayon
    mesure ici : les deux forcent `only_adjacent`, donc tout couple qu'ils touchent et dont la
    valeur est non observable s'AJOUTE au gisement. Ce chiffrage est donc un MINORANT."""
    rng = getattr(opts, "range", None)
    if rng is None:
        return {"decidable": False}                  # `TargetingRange` NON RE-LU -> `get_range` = None
    if rng.use_whole_board:
        # #419-r1-tr14-r5-r2-r1-r2-r1-r1-r1 : `get_range` ne rabat plus ce regime sur un `None`, il
        # rend le litteral natif `0x10000000001` = `{1, false, true}`. Le modele doit suivre le
        # CODE : la valeur est CONNUE, `only_adjacent` est faux, et ce sont les OPTIONS
        # (`options.Range.UseWholeBoard`) qui desarment les deux gates chez le consommateur -- pas
        # une absence de `Range`. Le decompte d'avant/apres, lui, est inchange : zero gate des deux
        # cotes.
        return {"decidable": True, "whole_board": True, "value_known": True,
                "only_adjacent": False,
                "avant_adjacence": False, "avant_distance": False,
                "apres_adjacence": False, "apres_distance": False}
    if rng.override_range is not None:
        value_known = True
    else:
        value_known = unit_weapon_range(vis, None) is not None
    if rng.override_range_func:
        value_known = False
    only_adj = _ranged_bool(rng.only_adjacent, vis)
    return {
        "decidable": True, "value_known": value_known, "only_adjacent": only_adj,
        # AVANT : `get_range` rendait None des que la valeur manquait -> AUCUN gate.
        "avant_adjacence": value_known and only_adj,
        "avant_distance": value_known and not only_adj,
        # APRES : le gate d'adjacence ne depend plus que de `only_adjacent`.
        "apres_adjacence": only_adj,
        "apres_distance": value_known and not only_adj,
    }


def run(verbose: bool = True) -> dict:
    cat = _catalogue()
    srcs = _options_sources()
    couples = 0
    gagnes = []            # gate d'adjacence ARME la ou il ne l'etait pas
    perdus = []            # un gate qui DISPARAIT : interdit
    inchanges_obs = 0      # couples a portee OBSERVABLE, qui doivent etre bit a bit identiques
    bouges_obs = []
    for origin, aid, opts in srcs:
        for vis in cat:
            g = _gate_state(opts, vis)
            if not g["decidable"]:
                continue
            couples += 1
            av = (g["avant_adjacence"], g["avant_distance"])
            ap = (g["apres_adjacence"], g["apres_distance"])
            if g["value_known"]:
                if av == ap:
                    inchanges_obs += 1
                else:
                    bouges_obs.append((origin, aid, vis, av, ap))
                continue
            if ap[0] and not av[0]:
                gagnes.append((origin, aid, vis))
            if (av[0] and not ap[0]) or (av[1] and not ap[1]):
                perdus.append((origin, aid, vis, av, ap))
    abilities = sorted({(o, a) for (o, a, _v) in gagnes})
    unites = sorted({v for (_o, _a, v) in gagnes})
    if verbose:
        print("=== catalogue %d unites x %d jeux d'options = %d couples DECIDABLES"
              % (len(cat), len(srcs), couples))
        print("  gate d'adjacence ARME par le correctif : %d couples" % len(gagnes))
        print("    sur %d jeux d'options et %d unites distinctes" % (len(abilities), len(unites)))
        par_origine = {}
        for (o, a, _v) in gagnes:
            par_origine.setdefault(o, set()).add(a)
        for o in sorted(par_origine):
            ids = sorted(par_origine[o])
            print("      %-16s %2d jeux : %s" % (o, len(ids), ", ".join(str(i) for i in ids[:14])
                                                 + (" ..." if len(ids) > 14 else "")))
        print("  couples a portee OBSERVABLE inchanges : %d (bouges : %d)"
              % (inchanges_obs, len(bouges_obs)))
        print("  gates PERDUS (regression) : %d" % len(perdus))
        print("\n  --- echantillon des unites nouvellement gatees (10 premieres) :")
        for v in unites[:10]:
            print("      %-28s weapons=%s" % (v, (GC.unit(v) or {}).get("weapons") or []))
    return {"couples": couples, "gagnes": gagnes, "perdus": perdus,
            "inchanges_obs": inchanges_obs, "bouges_obs": bouges_obs,
            "abilities": abilities, "unites": unites, "catalogue": len(cat)}


def couples_reels(verbose: bool = True) -> dict:
    """Le rayon de souffle REEL -- le produit cartesien ci-dessus est un MAJORANT (il apparie chaque
    jeu d'options a TOUTE unite). Ici on n'apparie que ce qui existe :

      * ATTAQUE NORMALE : le type que la fabrique pose reellement sur l'unite, via le foyer
        `custom_normal_attack` (mirror de `UnitFactory$$AddNormalAttackAbility`) ; `None` = repli sur
        le type generique `69`.
      * REGISTRE : les abilities que le KIT attribue a l'unite (`GC.unit_abilities`).

    ⚠ Les MACHINES OF WAR n'ont AUCUNE attaque normale (`MachineFactory$$Build` n'appelle jamais
    `AddNormalAttackAbility`, unique xref de code : `UnitFactory$$Build`) : leur volet ATTAQUE NORMALE
    est ecarte -- mais leurs abilities du REGISTRE, elles, comptent."""
    from engine.services.custom_normal_attack import custom_normal_attack
    reels, mow = [], []
    for vis in _catalogue():
        kit = GC.unit(vis) or {}
        if (kit.get("weapons") or []):
            continue                                     # portee observable -> hors gisement
        traits = {t if isinstance(t, str) else (t or {}).get("name")
                  for t in (kit.get("traits") or [])}
        if "MachineOfWar" in traits:
            mow.append(vis)
        else:
            name = custom_normal_attack(visual_id=vis)
            t = GC.ability_id(name) if name else 69
            opts = NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE.get(int(t)) if t else None
            if opts is not None:
                g = _gate_state(opts, vis)
                if g.get("apres_adjacence") and not g.get("avant_adjacence"):
                    reels.append(("attaque-normale", int(t), vis))
        ids = {a.get("id") for a in ((GC.unit_abilities(vis) or {}).get("active") or [])}
        for aid, cls in ABILITY_CLASSES.items():
            o = getattr(cls, "TARGETING_OPTIONS", None)
            if o is None or int(aid) not in ids:
                continue
            g = _gate_state(o, vis)
            if g.get("apres_adjacence") and not g.get("avant_adjacence"):
                reels.append(("registre", int(aid), vis))
    if verbose:
        par = {}
        for (o, a, v) in reels:
            par.setdefault((o, a), []).append(v)
        print("\n=== RAYON REEL (porteur x SES abilities) : %d couples, %d jeux d'options"
              % (len(reels), len(par)))
        for (o, a) in sorted(par):
            print("      %-16s %-6d %2d porteur(s) : %s"
                  % (o, a, len(par[(o, a)]), ", ".join(sorted(par[(o, a)])[:6])
                     + (" ..." if len(par[(o, a)]) > 6 else "")))
        print("      (MACHINES OF WAR ecartees, sans attaque normale : %d)" % len(mow))
    return {"reels": reels, "mow": mow}


def accord_modele_code(verbose: bool = True) -> dict:
    """LE CRAN QUI FAIT ROUGIR CE PROBE. Les etapes 1 et 2 raisonnent sur un MODELE de `get_range` ;
    un modele seul est un inventaire deguise en garde-fou -- il resterait VERT si le code repartait
    en arriere. Ici on APPELLE `get_range` sur un `State` synthetique et on confronte, couple par
    couple, `only_adjacent` et le tri-etat de `value`.

    L'etat synthetique porte une seule unite (visualId + tuile + owner) : c'est tout ce que
    `get_range` lit hors clamps, et les clamps sont inertes dessus (`state.effects` vide,
    `state.board` absent -> `should_apply_ranged_in_melee` rend False, tel qu'il est ecrit)."""
    from engine.runner.abilities.targeting import get_range
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State
    ecarts, verifies = [], 0
    # Le gisement suffit : ce sont les couples ou modele et code peuvent diverger. On y ajoute un
    # temoin a portee OBSERVABLE par jeu d'options, pour garder aussi le sens inverse.
    cat = _catalogue()
    sans_arme = [v for v in cat if not ((GC.unit(v) or {}).get("weapons") or [])]
    avec_arme = [v for v in cat if ((GC.unit(v) or {}).get("weapons") or [])]
    echantillon = sans_arme + avec_arme[:40]
    for origin, aid, opts in _options_sources():
        for vis in echantillon:
            attendu = _gate_state(opts, vis)
            st = State()
            ent = st.add_entity()
            ent.add_component(UnitComponent(visual_id=vis, alive=True))
            ent.add_component(PositionComponent(col=3, row=3))
            ent.add_component(OwnerComponent(team=0))
            cid = next(k for k, v in st.entities.items() if v is ent)
            rr = get_range(st, int(cid), opts)
            verifies += 1
            if not attendu["decidable"]:
                if rr is not None:
                    ecarts.append((origin, aid, vis, "attendu None (non decidable)", rr))
                continue
            if rr is None:
                ecarts.append((origin, aid, vis, "get_range a rendu None", attendu))
                continue
            if bool(rr.only_adjacent) != bool(attendu["only_adjacent"]):
                ecarts.append((origin, aid, vis, "only_adjacent", (rr.only_adjacent,
                                                                   attendu["only_adjacent"])))
            if (rr.value is not None) != bool(attendu["value_known"]):
                ecarts.append((origin, aid, vis, "tri-etat de value", (rr.value,
                                                                      attendu["value_known"])))
    if verbose:
        print("\n=== ACCORD MODELE <-> CODE : %d couples appeles, %d ecart(s)"
              % (verifies, len(ecarts)))
        for e in ecarts[:8]:
            print("      %s" % (e,))
    return {"verifies": verifies, "ecarts": ecarts}


def jumeau_toujours_none() -> bool:
    """Etage JUMEAU, celui qu'il ne faut PAS aligner. `TargetingQuery$$GetTilesInRange` teste
    `(int)range < 0` puis `(int)range == 0` AVANT `range._4_1_ OnlyAdjacent` : la valeur y EST lue
    quoi qu'il arrive, donc `tiles_in_range_reach` a RAISON de rendre `None` quand la portee d'arme
    n'est pas observable. Ce cran empeche une « correction par symetrie »."""
    from engine.services.ability_range import tiles_in_range_reach
    # 1146 `FloatingDeath_NormalAttack` n'est pas au registre -> on prend une ability a
    # `RANGE_ADJACENT_IF_MELEE_CASTER` et un porteur SANS ARME.
    sans_arme = [v for v in _catalogue()
                 if not ((GC.unit(v) or {}).get("weapons") or [])]
    if not sans_arme:
        raise RuntimeError("aucune unite sans arme au catalogue -- substrat suspect")
    return tiles_in_range_reach(1019, sans_arme[0]) is None      # 1019 StormOfWrath, TR statics+0x00


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    res = run(verbose=not a.quiet)
    rc = 0
    if not res["gagnes"]:
        print("[FAIL] RAYON VIDE : le correctif ne deplace aucun couple -- la mesure ne prouve rien")
        rc = 1
    if res["perdus"]:
        print("[FAIL] %d gate(s) PERDU(S) : le correctif en desarme un qui etait arme"
              % len(res["perdus"]))
        rc = 1
    if res["bouges_obs"]:
        print("[FAIL] %d couple(s) a portee OBSERVABLE ont bouge -- le correctif deborde"
              % len(res["bouges_obs"]))
        rc = 1
    rr = couples_reels(verbose=not a.quiet)
    if not rr["reels"]:
        print("[FAIL] RAYON REEL VIDE : aucun porteur reel touche -- le correctif serait theorique")
        rc = 1
    ac = accord_modele_code(verbose=not a.quiet)
    if ac["ecarts"]:
        print("[FAIL] %d ecart(s) MODELE <-> CODE : le chiffrage ci-dessus ne decrit plus `get_range`"
              % len(ac["ecarts"]))
        rc = 1
    ok = jumeau_toujours_none()
    print("  etage jumeau `tiles_in_range_reach` sur portee non observable -> %s"
          % ("None (CORRECT)" if ok else "NON None (aligne a tort !)"))
    if not ok:
        print("[FAIL] l'etage `GetTilesInRange` a ete aligne alors qu'il lit `Value` en PREMIER")
        rc = 1
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
