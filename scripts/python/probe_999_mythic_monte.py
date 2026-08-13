"""#999 -- LE MONTAGE MYTHIQUE MORD-IL ? Preuve par le natif, pas par le JSON qu'on a ecrit.

Le montage (`catalog_inject.equip_mythic`) ecrit trois champs du seed BC. Qu'ils soient ECRITS ne
prouve RIEN : les deux verrous de la voie tertiaire (config d'ability absente, niveau a 0)
echouent EN SILENCE -- l'unite se deploie, et l'ability n'est simplement jamais montee, ou faute a
la premiere lecture de variable.

Ce probe lit donc ce que le NATIF a monte, par le canal `unitAbilityStates` : le capteur y dumpe
le `TriggeredAbilityComponent+0x18` instance par instance, ou `raw[0]` = `AbilityName` et
`raw[10]` = la HIERARCHIE. La branche tertiaire d'`IdunBattle.Entities.Factories.UnitFactory$$
AddConfiguredAbilities` inscrit avec `TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState,
3)` -- donc la preuve recherchee est une entree de hierarchie **3** portant l'id de la mythique,
avec un `level >= 1`.

CE QUE LE PROBE REFUSE DE CONCLURE. Une absence d'entree ne dit pas *pourquoi* : il imprime alors
les hierarchies effectivement vues, pour distinguer « rien monte » de « monte ailleurs ».

Usage :
  python probe_999_mythic_monte.py --unit necroReanimator [--ability GuardianConstruct]
                                   [--level 1] [--board MC1_67] [--keep]
Sortie ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject  # noqa: E402
import rl_duel as R  # noqa: E402

# Rosters TEMOINS par faction du porteur : deux unites du pool de chaque cote, choisies pour
# EXISTER au rank 17 -- le probe ne mesure pas le combat, seulement le montage.
ROSTER_P = "necroDestroyer,necroWarden"
ROSTER_A = "tyranParasite,tyranTyrantGuard"


def _unwrap(x):
    if isinstance(x, dict) and "result" in x:
        return x["result"]
    return x


def main() -> int:
    ap = argparse.ArgumentParser(description="#999 -- le montage mythique mord-il ?")
    ap.add_argument("--unit", required=True, help="unitId porteur (MoW lineup)")
    ap.add_argument("--ability", default=None, help="nom de la mythique (derive si omis)")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--sans-montage", action="store_true",
                    help="CONTRE-BRAS : monte le MEME porteur SANS --equip-mythic. L'inscription "
                         "de hierarchie 3 doit DISPARAITRE -- sans quoi le bras positif ne "
                         "prouve rien (le porteur la porterait deja). Inverse le verdict.")
    a = ap.parse_args()

    ability = a.ability
    if ability is None:
        _uid, ability, _lvl = catalog_inject.parse_mythic_spec(a.unit)
    aid = catalog_inject.triggered_ability_id(ability)
    carriers = catalog_inject.mythic_carriers(ability)
    print("=== ETAGE 0 : ce qu'on monte ===")
    print("  porteur   = %s" % a.unit)
    print("  ability   = %s (TriggeredAbilityType=%d)" % (ability, aid))
    print("  porteurs  = %s" % carriers)
    print("  paliers   = %d ; niveau demande = %d"
          % (catalog_inject.ability_level_count(ability), a.level))

    sf = a.state_file or str(Path(__file__).resolve().parents[2] / "logs"
                             / ("probe999_%s.json" % a.unit))
    argv = ["build", "--seed", str(a.seed), "--board", a.board,
            "--p-units", ROSTER_P, "--a-units", ROSTER_A,
            "--p-mow", a.unit,
            "--state-file", sf]
    if a.sans_montage:
        # Le porteur doit quand meme ETRE la : sans lui, le contre-bras rendrait un vide qui
        # prouverait l'absence du PORTEUR, pas celle du MONTAGE. On l'injecte au catalogue par
        # `augment` NU -- la primitive que `write_mythic_seed_bc` appelle AVANT `equip_mythic`,
        # donc exactement le meme arbre moins les trois ecritures tertiaires.
        seed = catalog_inject._load_seed(None)
        bc, added, _ab, _unres = catalog_inject.augment(seed, [a.unit], rank=17)
        aug = Path(sf).with_name("probe999_seedaug_%s.json" % a.unit)
        aug.parent.mkdir(parents=True, exist_ok=True)
        aug.write_text(json.dumps(bc), encoding="utf-8")
        print("  [contre-bras] seed augmente (+%d unites %s) sans aucune ecriture tertiaire : %s"
              % (len(added), added, aug))
        argv[-2:-2] = ["--seed-bc", str(aug)]
    else:
        argv[-2:-2] = ["--equip-mythic", "%s:%s:%d" % (a.unit, ability, a.level)]
    print()
    print("=== ETAGE 1 : build ===")
    rc = R.main(argv)
    if rc != 0:
        print("  BUILD ECHOUE rc=%s -- rien n'est conclu du montage" % rc)
        return 2

    st = json.loads(Path(sf).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    print("  runnerId=%s" % rid)

    import rl_collect_batch as B
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(B._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    try:
        print()
        print("=== ETAGE 2 : ce que le NATIF a monte (unitAbilityStates) ===")
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60) or {}
        units = uas.get("units")
        if units is None:
            print("  CANAL MUET : %r -- rien n'est conclu" % (uas.get("error"),))
            return 2
        ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
        noms = {u.get("id"): (u.get("unitId") or u.get("visualId") or "?")
                for u in (ob.get("units") or [])}

        trouve = []
        hierarchies_vues: dict = {}
        for su in units:
            eid = su.get("entityId")
            for t in (su.get("triggered") or []):
                raw = t.get("raw") or []
                if len(raw) < 11:
                    continue
                nom_id, hier = raw[0], raw[10]
                hierarchies_vues.setdefault(hier, 0)
                hierarchies_vues[hier] += 1
                if hier == 3:
                    print("  entite %-4s (%-22s) TERTIAIRE id=%-5s level=%s mult=%s"
                          % (eid, noms.get(eid, "?"), nom_id, t.get("level"), t.get("mult")))
                    if nom_id == aid:
                        trouve.append((eid, t.get("level"), t.get("mult")))

        print("  hierarchies vues (hierarchie -> nb d'inscriptions) : %s"
              % dict(sorted(hierarchies_vues.items())))
        print()
        print("=== VERDICT ===")
        if a.sans_montage:
            # CONTRE-BRAS : le verdict est INVERSE. Une inscription trouvee ici voudrait dire que
            # le porteur portait DEJA la mythique, donc que le bras positif ne mesurait rien.
            if trouve:
                print("  CONTRE-BRAS ROUGE : sans --equip-mythic, l'id %d est DEJA monte en "
                      "hierarchie 3 (%s) -- le bras positif ne prouve donc RIEN." % (aid, trouve))
                return 1
            print("  CONTRE-BRAS VERT : sans --equip-mythic, AUCUNE inscription de hierarchie 3 "
                  "portant l'id %d. Le montage est bien ce qui la pose." % aid)
            return 0
        if not trouve:
            print("  MONTAGE MUET : aucune inscription de hierarchie 3 portant l'id %d." % aid)
            print("  (le natif inscrit la tertiaire par TriggeredAbilityComponent$$TryAdd(.., 3) ;")
            print("   une absence ici signifie que UnitFactory$$AddConfiguredAbilities n'a rien vu)")
            return 1
        for eid, lvl, mult in trouve:
            if lvl is None or lvl < 1:
                print("  MONTAGE ARME MAIS VERROUILLE : entite %s level=%r -- "
                      "Idun.Shared.Level$$ToZeroBasedIndex LEVE sur <= 0" % (eid, lvl))
                return 1
            print("  MONTE : entite %s (%s) porte %s (id=%d) en hierarchie 3, level=%s mult=%s"
                  % (eid, noms.get(eid, "?"), ability, aid, lvl, mult))
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
