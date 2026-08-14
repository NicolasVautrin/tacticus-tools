"""#1042 -- `WisdomOfTheAncients` (mythique de la MoW `ultraDreadnought` << Galatian >>) : l'AURA
de reduction de degat, mesuree etage par etage.

Ce probe n'a PAS de port a valider -- l'effet 1445 n'entre pas dans `EFFECT_CLASSES` (verrou de
RARETE, cf. `docs/rl/case-1042-wisdom-of-the-ancients.md`). Il etablit le GROUND TRUTH de ce que le
decompile ecrit, avec des contre-epreuves qui SEPARENT chaque etage.

RE (mirror du decompile, build `rnca9r7q6c`) :

  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WisdomOfTheAncientsAbility$$CreateTrigger`
      = DSLTriggers.OnOwnerSpecificAbilityInit(0x5ab = 1451)
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WisdomOfTheAncientsAbility$$CreateBehaviour`
      = DSLBehaviors.AddEffect(0x5a5 = 1445, AbilityStateReference,
                               source = Owner@<DSLSelectors+0x30>, targets = Owner, options = ZERO)

  `IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect$$ValidCharacter`
      ValidCharacter(x) = UnitsWithRarity(x, Rarity.Mythic = 5, OnlyAliveAndTargetable = 3)
  `IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect$$CreateTargetSelector`
      A = ValidCharacter( AdjacentFriends(Owner@<+0x30>, unique = true, 3) )
      B = ValidCharacter( Friends(of = Owner@<+0x30>, entities = AllUnits@<+0x20>, 3) )
      F = Filter( B, AmountIsGreaterThanZero(
                         UnitsWithTrait( ValidCharacter( AdjacentFriends(
                                             ActiveTarget@<+0x68>, unique = true, 3) ),
                                         UnitTrait.Hero = 0x10, 3 ) ) )
      return ConditionalSelector( IsMachine(Owner@<+0x30>), ifTrue = F, ifFalse = Unique(A + F) )
  `...WisdomOfTheAncients_DamageReductionEffect$$CreateEffectDamageMalusForDefense`
      Nullable<EffectBonus>( EffectBonus.ForPercentDecrease(
          get_OwnerIsTarget, ConfigVar(AbilityVariableType.dmgReductionPct = 0x46, ...) ) )

MONTAGE -- l'aura est du cote ADVERSE, et c'est ce qui rend le degat lisible : `decisionView.
attackPlans` ne publie que MES unites, donc la prediction NATIVE contre un defenseur affecte ne
s'obtient qu'en placant le porteur en face.

   team 2 (l'aura)   P1 (1,1) - P2 (2,1) - P3 (3,1)   chaine ; d(P1,P3) = 2
                     H  (5,7) - X  (6,7)              paire isolee, d >= 7 de la chaine
   team 1 (moi)      A1 (2,2) adjacent a P2 ; A2 (6,6) adjacent a X ; A3 (0,8) hors de tout

`H` est FORCE a `Rarity = 4` dans TOUS les bras (`--unit-stat`) : c'est ce qui rend `X` un TEMOIN.
  * `X` n'a qu'un voisin ami, `H`, non-Mythic -> `F` ne le contient PAS ;
  * `A` = `ValidCharacter(AdjacentFriends(Owner))` le contient des que l'Owner est `H`.
Donc `X` DISCRIMINE les deux branches du `ConditionalSelector`, et rien d'autre ne le fait :
sur la MoW porteuse, `AdjacentFriends(Owner)` est structurellement VIDE (une MoW n'a ni `pos` ni
`feet` -- MESURE), donc `A = {}` et les deux branches COINCIDENT. C'est le bras `greffe`
(`--allow-unlisted-mythic` sur `astraCreed`, un porteur ON-BOARD donc `IsMachine(Owner) == false`)
qui sort de ce regime degenere.

BRAS et attendus :
  sans-mythique          aucun effet 1445                     (contre-epreuve d'existence)
  mow                    targetIds = {P1,P2,P3}, X ABSENT     (branche ifTrue = F)
  greffe                 targetIds = {P1,P2,P3,X}, X PRESENT  (branche ifFalse = Unique(A + F))
  mow --rarity P1=4      targetIds = {P2,P3}                  (etage rarete EXTERIEUR, sur B)
  mow --rarity P2=4      targetIds = {}                       (etage rarete INTERIEUR, sous le Filter)
  mow --traits P2=...,NPC  targetIds = {P2}                   (le noeud `UnitsWithTrait(., Hero)`)

⚠ LE BRAS `--traits` EXIGE UN TRAIT PORTEUR (`NPC` ou `Summon`), sans quoi il ne mesure RIEN --
`IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` RAJOUTE `Hero` a toute unite qui n'est
ni `NPC`, ni `Summon`, ni enfant, APRES que la fabrique a pose les traits de `BC.Units[].Traits`.
Le garde de l'etage 1bis REFUSE (rc 2) si `Hero` survit. Detail : `docs/rl/case-1044-mur-des-traits.md`.

Usage :
  python probe_1042_wisdom_of_the_ancients_live.py --bras mow --level 4
  python probe_1042_wisdom_of_the_ancients_live.py --bras sans-mythique
  python probe_1042_wisdom_of_the_ancients_live.py --bras mow --rarity adeptRetributor=4
  python probe_1042_wisdom_of_the_ancients_live.py --bras greffe
  python probe_1042_wisdom_of_the_ancients_live.py --bras mow --traits "adeptCanoness=Imperial,ActOfFaith,NPC"
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

PORTEUR_MOW = "ultraDreadnought"        # MoW << Galatian >>, seul porteur `lineup` de la mythique
PORTEUR_GREFFE = "astraCreed"           # porteur ON-BOARD greffe : `IsMachine(Owner) == false`
ABILITY = "WisdomOfTheAncients"
EFFECT_TYPE = 1445                      # `EffectType.WisdomOfTheAncients_DamageReduction` = 0x5a5

#: L'aura vit sur l'equipe ADVERSE (cf. l'en-tete : c'est ce qui rend `attackPlans` exploitable).
P1_VIS, P1_POS = "adeptRetributor", (1, 1)
P2_VIS, P2_POS = "adeptCanoness", (2, 1)
P3_VIS, P3_POS = "adeptHospitaller", (3, 1)
H_VIS, H_POS = PORTEUR_GREFFE, (5, 7)
X_VIS, X_POS = "astraBullgryn", (6, 7)
AURA_UNITS = [(P1_VIS, P1_POS), (P2_VIS, P2_POS), (P3_VIS, P3_POS), (H_VIS, H_POS), (X_VIS, X_POS)]

#: Mes attaquants : un par defenseur temoin. On ne compare JAMAIS A1 a A2 (unites differentes),
#: on compare CHAQUE couple (attaquant, defenseur) ENTRE LES BRAS.
A1_VIS, A1_POS = "blackTerminator", (2, 2)      # adjacent a P2  -> defenseur AFFECTE
A2_VIS, A2_POS = "bloodDeathCompany", (6, 6)    # adjacent a X   -> defenseur TEMOIN
#: hors de tout (d >= 5 de chaque unite placee) : evite un 2v5 fragile sans polluer l'adjacence.
#: ⚠ (0,8) est un `Block` de MC1_67 -- `AddUnitOperation$$AreTilesDisallowedAndLog` y fait un
#: RETOUR NUL SILENCIEUX, que `rl_duel build` rattrape en rc 3. Tuile LUE dans le dump du board.
A3_VIS, A3_POS = "bloodSanguinary", (0, 6)
MES_UNITS = [(A1_VIS, A1_POS), (A2_VIS, A2_POS), (A3_VIS, A3_POS)]

BOARD = "MC1_67"                        # 7x9, entierement Grass : toute tuile est posable
#: `H` n'est JAMAIS Mythic -- c'est l'invariant qui fait de `X` un discriminant (cf. en-tete).
RARITE_H = 4


def _unwrap(x):
    return x["result"] if isinstance(x, dict) and "result" in x else x


def _lignes(dv: dict):
    """Les entites porteuses d'effets : `decisionView.units` ET `decisionView.mows`.

    ⚠ Une MoW n'est PAS dans `units`, et c'est elle qui PORTE l'effet d'aura dans le bras `mow`."""
    return list(dv.get("units") or []) + list(dv.get("mows") or [])


def _cibles_de_l_aure(dv: dict, effect_type: int) -> set:
    """Union des `targetIds` de toutes les entrees d'effet du type demande.

    ⚠ UNE AURE NE SE LIT PAS SUR SA CIBLE : `decisionView` publie l'entite-EFFET une seule fois,
    portee par sa SOURCE, et c'est son champ `targetIds` qui enumere les affectes (#1024)."""
    hit = set()
    for u in _lignes(dv):
        for e in (u.get("effects") or []):
            if e.get("effectType") == effect_type:
                hit.update(e.get("targetIds") or [])
    return hit


def _plans_par_tuile(dv: dict, caster: int, target: int, ability_id) -> dict:
    """{(col,row): (dmgMin, dmgMax)} pour un triplet (caster, cible, ability).

    Source : `decisionView.attackPlans[].evals[].ranked[]`, la prediction NATIVE PAR TUILE de
    depart. On la prend par tuile (jamais << le meilleur >>) pour que la comparaison inter-bras
    porte sur des points identiques."""
    out = {}
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") != caster:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("targetId") != target or ev.get("abilityId") != ability_id:
                continue
            for r in (ev.get("ranked") or []):
                out[(r.get("col"), r.get("row"))] = (r.get("dmgMin"), r.get("dmgMax"))
    return out


def _geometrie():
    """Assertionne la geometrie PILOTEE plutot que de la subir (feedback_drive_positions)."""
    assert hexgeo.distance(P1_POS, P2_POS) == 1
    assert hexgeo.distance(P2_POS, P3_POS) == 1
    assert hexgeo.distance(P1_POS, P3_POS) == 2      # P1 et P3 ne se voient PAS
    assert hexgeo.distance(H_POS, X_POS) == 1
    assert min(hexgeo.distance(X_POS, p) for p in (P1_POS, P2_POS, P3_POS)) >= 2
    assert min(hexgeo.distance(H_POS, p) for p in (P1_POS, P2_POS, P3_POS)) >= 2
    assert hexgeo.distance(A1_POS, P2_POS) == 1
    assert hexgeo.distance(A2_POS, X_POS) == 1
    assert min(hexgeo.distance(A3_POS, p)
               for p in (P1_POS, P2_POS, P3_POS, H_POS, X_POS, A1_POS, A2_POS)) >= 2


def main() -> int:
    ap = argparse.ArgumentParser(description="#1042 -- WisdomOfTheAncients, ground truth live")
    ap.add_argument("--bras", choices=["mow", "greffe", "sans-mythique"], default="mow")
    ap.add_argument("--level", type=int, default=4)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--rarity", action="append", default=[],
                    help="ECRIT `BC.Units[<vis>].Rarity` APRES la normalisation, "
                         "'<visualId>=<n>', repetable. `rl_duel build` impose `targetRarity = 5` "
                         "(`rl_collect_batch._TARGET_RARITY`) : sans ce levier tout est Mythic et "
                         "les trois etages `UnitsWithRarity` sont uniformement VRAIS -- regime "
                         "DEGENERE dans lequel un port sans gate serait faussement d'accord.")
    ap.add_argument("--traits", action="append", default=[],
                    help="REECRIT `BC.Units[<vis>].Traits`, '<visualId>=<Trait>[,<Trait>]', "
                         "repetable. SEUL levier qui exerce `UnitsWithTrait(..., UnitTrait.Hero)` : "
                         "toute unite `lineup` du pool porte `Hero`, donc ce noeud est lui aussi "
                         "uniformement VRAI par defaut. Retirer `Hero` du MILIEU de la chaine doit "
                         "laisser le milieu VISE (ses deux voisins restent des Heros Mythiques) et "
                         "eteindre ses DEUX voisins -- signature {P2} seul, distincte des deux "
                         "autres bras. AJOUTER `NPC` A LA LISTE (#1044) : sans ce trait porteur "
                         "le natif re-pose `Hero` et le bras ne mesure rien (rc 2). MESURE "
                         "2026-08-14 : `adeptCanoness=Imperial,ActOfFaith,NPC` rend bien "
                         "targetIds = [87] = {P2}, contre [85,87,89] au bras `mow` nu.")
    a = ap.parse_args()

    _geometrie()

    import catalog_inject  # noqa: E402
    import gameconfig  # noqa: E402

    cfg = gameconfig.ability(ABILITY) or {}
    paliers = (cfg.get("variables") or {}).get("dmgReductionPct") or []
    pct = paliers[a.level - 1] if 1 <= a.level <= len(paliers) else None
    print("=== ETAGE 0 : ce que le gameconfig dit ===")
    print("  ability = %s (TriggeredAbilityType=%s) -> EffectType %d"
          % (ABILITY, catalog_inject.triggered_ability_id(ABILITY), EFFECT_TYPE))
    print("  dmgReductionPct = %s (rarity-flag: %s)"
          % (paliers, cfg.get("variablesAffectedByRarityBonus")))
    print("  bras = %s ; niveau %d -> dmgReductionPct attendu = %s" % (a.bras, a.level, pct))

    rar = dict(x.split("=", 1) for x in a.rarity)
    rar.setdefault(H_VIS, str(RARITE_H))            # invariant du montage, cf. en-tete
    tra = {k: [t for t in v.split(",") if t] for k, v in (x.split("=", 1) for x in a.traits)}
    print("  rarites forcees (APRES normalisation) : %s" % rar)
    print("  traits reecrits                       : %s" % tra)

    sf = a.state_file or str(Path(__file__).resolve().parents[2] / "logs"
                             / ("probe1042_woa_%s_l%d%s%s.json"
                                % (a.bras, a.level,
                                   "".join("_%s%s" % (k[:6], v) for k, v in sorted(rar.items())),
                                   "".join("_t%s" % k[:6] for k in sorted(tra)))))
    argv = ["build", "--seed", str(a.seed), "--board", a.board,
            "--p-units", ",".join(v for v, _ in MES_UNITS),
            "--a-units", ",".join(v for v, _ in AURA_UNITS),
            "--a-mow", PORTEUR_MOW,
            "--unit-stat", ";".join("%s:Rarity=%s" % (k, v) for k, v in sorted(rar.items()))]
    for vis, traits in sorted(tra.items()):
        argv += ["--unit-stat", "%s:Traits=%s" % (vis, json.dumps(traits))]
    for vis, pos in MES_UNITS:
        argv += ["--place", "%s:%d,%d" % (vis, pos[0], pos[1])]
    for vis, pos in AURA_UNITS:
        argv += ["--a-place", "%s:%d,%d" % (vis, pos[0], pos[1])]
    if a.bras == "mow":
        argv += ["--equip-mythic", "%s:%s:%d" % (PORTEUR_MOW, ABILITY, a.level)]
    elif a.bras == "greffe":
        argv += ["--equip-mythic", "%s:%s:%d" % (PORTEUR_GREFFE, ABILITY, a.level),
                 "--allow-unlisted-mythic"]
    argv += ["--state-file", sf]

    print()
    print("=== ETAGE 1 : build ===")
    if R.main(argv) != 0:
        print("  BUILD ECHOUE -- rien n'est conclu")
        return 2
    st = json.loads(Path(sf).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    print("  runnerId=%s  bras=%s" % (rid, a.bras))

    import rl_collect_batch as B  # noqa: E402
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(B._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    try:
        dv = rpc("decisionView", {"runnerId": rid}, 120) or {}
        ids = {}
        for u in _lignes(dv):
            ids.setdefault(u.get("visualId"), u.get("id"))
        besoin = [P1_VIS, P2_VIS, P3_VIS, H_VIS, X_VIS, A1_VIS, A2_VIS]
        if any(ids.get(v) is None for v in besoin):
            print("  MONTAGE INCOMPLET %s -- rien n'est conclu" % (ids,))
            return 2

        # ETAGE 1bis -- la MUTATION a-t-elle MORDU ? `combatSnapshot.units[].traits` (#233) publie
        # les traits REELLEMENT portes en bataille, pas ceux du gameconfig. Sans ce cran, un
        # `--traits` qui n'atteindrait pas `BaseUnitComponent` rendrait un bras VERT pour la
        # mauvaise raison (le set ne bouge pas... parce que rien n'a bouge).
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
        tsnap = {}
        for u in (snap.get("units") or []):
            tsnap[u.get("entityId")] = u.get("traits")
        if tra:
            # ⚠ `combatSnapshot.units[].traits` publie des ORDINAUX, pas des noms : comparer par
            # membre d'enum, jamais par chaine (une comparaison de chaines rendait ce bras VERT
            # alors que `Hero` etait toujours porte -- mesure #1042).
            from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
            print()
            print("=== ETAGE 1bis : la mutation `--traits` a-t-elle MORDU ? ===")
            for vis, attendus in sorted(tra.items()):
                vus = tsnap.get(ids.get(vis))
                print("  %-22s (u%s) traits en bataille = %s (demandes : %s)"
                      % (vis, ids.get(vis), vus, attendus))
                if vus is None:
                    print("    NON MESURE : `combatSnapshot` ne publie pas les traits de cette"
                          " entite -- rien n'est conclu de ce bras.")
                    return 2
                if int(UnitTrait.Hero) in [int(t) for t in vus] and "Hero" not in attendus:
                    print("    MUTATION NON MORDUE : `UnitTrait.Hero` (%d) est TOUJOURS porte"
                          " alors que `BC.Units[].Traits` a ete reecrit -- ce bras ne mesure PAS"
                          " le noeud `UnitsWithTrait(..., UnitTrait.Hero)`, et un set inchange n'y"
                          " prouve donc RIEN." % int(UnitTrait.Hero))
                    # LA SORTIE EST CONNUE DEPUIS #1044, et elle tient en un mot ajoute a la
                    # demande : `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` passe
                    # APRES la fabrique et RAJOUTE `Hero` a toute unite qui n'est ni `NPC`, ni
                    # `Summon`, ni enfant. Ajouter un TRAIT PORTEUR a `--traits` fait retourner
                    # ce foyer sans rien ecrire.
                    print("    SORTIE (#1044) : ajouter `NPC` a la liste --"
                          " `--traits \"%s=%s,NPC\"`. Voir `probe_1044_levier_traits.sans_hero`"
                          " et `docs/rl/case-1044-mur-des-traits.md`."
                          % (vis, ",".join(attendus) if attendus else ""))
                    return 2

        print()
        print("=== ETAGE 2 : l'AURA -- qui porte %d, et qui VISE-T-IL ? ===" % EFFECT_TYPE)
        for u in _lignes(dv):
            print("  u%-4s %-22s team=%s pos=%s feet=%s effets=%s"
                  % (u.get("id"), u.get("visualId"), u.get("team"), u.get("pos"), u.get("feet"),
                     [(e.get("effectType"), e.get("name"), e.get("targetIds"))
                      for e in (u.get("effects") or [])]))
        vises = _cibles_de_l_aure(dv, EFFECT_TYPE)
        roles = {"P1": P1_VIS, "P2": P2_VIS, "P3": P3_VIS, "H": H_VIS, "X": X_VIS}
        vu = {k: (ids[v] in vises) for k, v in roles.items()}
        print("  targetIds de l'effet %d : %s" % (EFFECT_TYPE, sorted(vises)))
        print("  par role : %s" % vu)

        namap = R._normal_ability_map(dv)
        a1, a2 = ids[A1_VIS], ids[A2_VIS]
        p2, x = ids[P2_VIS], ids[X_VIS]
        pl_aff = _plans_par_tuile(dv, a1, p2, namap.get(a1))
        pl_tem = _plans_par_tuile(dv, a2, x, namap.get(a2))
        print()
        print("=== ETAGE 3 : prediction NATIVE, par tuile de depart ===")
        print("  -- AFFECTE : %s u%s -> %s u%s (ability %s)" % (A1_VIS, a1, P2_VIS, p2,
                                                                namap.get(a1)))
        for k in sorted(pl_aff, key=lambda kk: (kk[0] is None, kk)):
            print("     depuis %-8s : %s" % (k, pl_aff[k]))
        print("  -- TEMOIN  : %s u%s -> %s u%s (ability %s)" % (A2_VIS, a2, X_VIS, x,
                                                               namap.get(a2)))
        for k in sorted(pl_tem, key=lambda kk: (kk[0] is None, kk)):
            print("     depuis %-8s : %s" % (k, pl_tem[k]))

        out = Path(sf).with_suffix(".plans.json")
        out.write_text(json.dumps({
            "bras": a.bras, "level": a.level, "rarites": rar, "traits": tra,
            "ids": {k: ids[v] for k, v in roles.items()},
            "vises": sorted(vises), "parRole": vu,
            "affecte": {"attaquant": a1, "cible": p2, "ability": namap.get(a1),
                        "plans": {"%s,%s" % k: v for k, v in pl_aff.items()}},
            "temoin": {"attaquant": a2, "cible": x, "ability": namap.get(a2),
                       "plans": {"%s,%s" % k: v for k, v in pl_tem.items()}},
        }), encoding="utf-8")
        print("  [plans ecrits dans %s]" % out)

        print()
        print("=== VERDICT (%s ; rarites %s ; traits %s) ===" % (a.bras, rar, tra))
        if a.bras == "sans-mythique":
            if vises:
                print("  CONTRE-EPREUVE ROUGE : l'effet %d existe SANS --equip-mythic (%s) -- les"
                      " bras positifs ne prouveraient rien." % (EFFECT_TYPE, sorted(vises)))
                return 1
            print("  CONTRE-EPREUVE VERTE : aucun effet %d. (plans ecrits pour la comparaison"
                  " inter-bras)" % EFFECT_TYPE)
            return 0
        if not vises:
            print("  AUCUNE CIBLE : soit un gate a tout eteint (bras attendu), soit le montage ne"
                  " pose pas l'aura -- comparer au bras `mow` sans `--rarity`/`--traits`.")
            return 0 if (a.rarity or a.traits) else 1
        if vu["H"]:
            print("  INATTENDU : `H` (Rarity=%s) est VISE alors que les TROIS etages"
                  " `UnitsWithRarity` devraient l'exclure." % rar.get(H_VIS))
            return 1
        if a.bras == "mow" and vu["X"]:
            print("  INATTENDU : `X` est VISE avec le porteur MoW -- la branche `ifTrue = F` du"
                  " `ConditionalSelector` ne serait alors pas celle qui s'applique.")
            return 1
        if a.bras == "greffe" and not vu["X"]:
            print("  INATTENDU : `X` n'est PAS vise avec un porteur ON-BOARD -- la branche"
                  " `ifFalse = Unique(A + F)` n'apporterait alors rien.")
            return 1
        print("  CONFORME au decompile : %s" % vu)
        print("  (le facteur de degat se lit en comparant ce .plans.json a celui du bras"
              " `sans-mythique` -- ratio attendu 1 - %s/100 sur l'AFFECTE, 1.0 sur le TEMOIN)" % pct)
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
