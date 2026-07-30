#!/usr/bin/env python
"""Probe #323 -- les VOIES par lesquelles une unite porte une ability, et le RE-BALAYAGE des
verdicts « 0 porteur » deja rendus.

POURQUOI. `unit_map.py find --ability` ne lisait que `activeAbilities` + `passiveAbilities`. Il
rendait donc « 0 unite » pour toute ability accordee par une RELIQUE -- et ce zero a ete lu comme
une preuve de mort : #310 a classe `NetherRealmCasket_LivingMetalBonusEffect` (effet 1462) DEAD,
alors que trois heros du POOL la portent et que `necroSpyder` l'a EQUIPEE dans le seed BC
(`Units[].TertiaryAbility = 1462`). C'est la faute que le depot denonce partout -- classer par un
outil aveugle a une voie -- appliquee a l'outil de RECENSEMENT lui-meme.

Ce probe rend QUATRE mesures, toutes DERIVEES (rien d'herite) :

  * volet A -- la table de COUVERTURE : 5 voies derivables du gameconfig, 4 assumees NON couvertes ;
  * volet B -- le GISEMENT du faux negatif : les abilities qu'un `find --ability` d'avant #323
    rendait a zero alors qu'elles ont des porteurs ;
  * volet C -- le RE-BALAYAGE de `docs/rl/` : combien de verdicts « 0 porteur / aucune unite »
    deja ecrits portent sur une ability du gisement B (donc sont FAUX ou a re-adjuger) ;
  * volet D -- l'effet de bord ASSUME : compter les reliques dans la classification `mech` retire
    des unites de l'ensemble « cible VANILLE » (elles portaient un modificateur qu'on ignorait).

Volet E (gate de confrontabilite) : `rl_duel build --list-pool` repond a une AUTRE question (quels
unitIds normalisent), il n'est donc pas « aveugle aux reliques » au sens de unit_map -- mais il ne
dit RIEN de la relique EQUIPEE, qui vit dans `BC.Units[].TertiaryAbility`. Le volet le mesure et
distingue les deux. Tri-etat sur le pool (None = pas mesure), meme discipline que `host_inputs.py`.

ASCII only (cp1252). Usage:
    python probe_323_ability_carrier_voies.py            # volets A-D (100% offline)
    python probe_323_ability_carrier_voies.py --pool     # + volet E (RPC buildNormalizedBC)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import gameconfig as GC
import unit_map as UM

ROOT = Path(__file__).resolve().parents[2]      # racine du CHECKOUT (jamais un chemin absolu)

# Les tournures par lesquelles une fiche prononce un verdict « aucun porteur ». Volontairement
# LARGE : mieux vaut adjuger a la main quelques faux positifs que rater un residu ferme a tort.
ZERO_VERDICT = re.compile(
    r"(0\s+unit|0\s+porteur|aucun\s+porteur|aucune\s+unit|aucun\s+chemin|sans\s+porteur"
    r"|AUCUN\s+porteur|n'a\s+AUCUN\s+porteur|aucune\s+entree)", re.I)
# Un identifiant d'ability tel qu'il apparait dans les fiches : entre backticks, ou en CamelCase nu.
TOKEN = re.compile(r"`([A-Za-z0-9_:]+)`|\b([A-Z][A-Za-z0-9]{3,})\b")


def _legacy_carriers(kits: list[dict], needle: str) -> list[str]:
    """Ce que `find --ability` rendait AVANT #323 : `activeAbilities` + `passiveAbilities` seuls."""
    n = needle.lower()
    return [k["id"] for k in kits
            if any(n in a.lower() for a in (k.get("voies") or {}).get("active", []))
            or any(n in a.lower() for a in (k.get("voies") or {}).get("passive", []))]


def _all_carriers(kits: list[dict], needle: str) -> list[tuple[str, str, list[str]]]:
    out = []
    for k in kits:
        vs = UM.carrier_voies(k, needle)
        if vs:
            out.append((k["id"], k["kind"], vs))
    return out


def volet_a(kits: list[dict]) -> None:
    print("=== VOLET A -- table de COUVERTURE des voies d'attribution ===")
    print("-- COUVERTES (derivables du gameconfig) :")
    for v in UM.VOIE_KEYS:
        src = ("items[*].abilityId + allowedUnits" if v == "item"
               else "units.<kind>.<id>." + UM.UNIT_ABILITY_FIELDS[v])
        carriers = [k for k in kits if (k.get("voies") or {}).get(v)]
        abils = {a for k in carriers for a in (k.get("voies") or {}).get(v, [])}
        print("   %-8s %-42s %4d unites, %3d abilities" % (v, src, len(carriers), len(abils)))
    print("-- NON couvertes (ASSUMEES) :")
    for name, why in UM.VOIES_NON_COUVERTES:
        print("   %-10s %s" % (name, why))


def volet_b(kits: list[dict]) -> dict:
    """Le gisement : abilities a porteurs REELS que la lecture d'avant #323 rendait a zero."""
    print("\n=== VOLET B -- gisement du faux negatif (abilities invisibles avant #323) ===")
    by_voie: dict[str, set] = {v: set() for v in UM.VOIE_KEYS}
    for k in kits:
        for v, names in (k.get("voies") or {}).items():
            by_voie[v] |= set(names)
    legacy_visible = by_voie["active"] | by_voie["passive"]
    invisible = (by_voie["relic"] | by_voie["mythic"] | by_voie["item"]) - legacy_visible
    print("   abilities du catalogue                       : %d" % len(GC._index()["abilities"]))
    print("   visibles par l'ancienne lecture (act+pass)   : %d" % len(legacy_visible))
    print("   INVISIBLES avant #323 (relic|mythic|item)    : %d" % len(invisible))
    detail: dict[str, list] = {}
    for a in sorted(invisible):
        carriers = _all_carriers(kits, a)
        # `carrier_voies` matche par SOUS-CHAINE (semantique historique de `find --ability`) :
        # on ne retient que les porteurs qui portent EXACTEMENT ce nom, sinon un prefixe commun
        # gonflerait le compte.
        exact = [(uid, kind, vs) for uid, kind, vs in carriers
                 if any(a in ((next(kk for kk in kits if kk["id"] == uid).get("voies") or {})
                              .get(v, [])) for v in vs)]
        detail[a] = exact
        kinds = sorted({kind for _, kind, _ in exact})
        voies = sorted({v for _, _, vs in exact for v in vs})
        print("     %-28s %2d porteurs  kinds=%-22s voies=%s"
              % (a, len(exact), ",".join(kinds), ",".join(voies)))
    lineup_only = [a for a, c in detail.items() if any(kind == "lineup" for _, kind, _ in c)]
    print("   dont %d ont AU MOINS UN porteur `lineup` (hero/MoW -- candidat confrontable) : %s"
          % (len(lineup_only), sorted(lineup_only)))
    return detail


def volet_c(kits: list[dict], gisement: dict) -> int:
    """RE-BALAYAGE de `docs/rl/` : les verdicts « 0 porteur » deja rendus tiennent-ils ?

    HEURISTIQUE ASSUMEE : on lit de la PROSE, pas une structure. Le probe rend des CANDIDATS a
    adjuger, jamais un verdict automatique -- et c'est ce que la fiche du cas tranche ligne a ligne."""
    print("\n=== VOLET C -- re-balayage des verdicts « 0 porteur » de docs/rl/ ===")
    docs = sorted((ROOT / "docs" / "rl").rglob("*.md"))
    known = set(GC._index()["abilities"])
    lines_scanned = 0
    verdict_lines = 0
    hits: list[tuple[str, int, str, str, int]] = []
    # FENETRE de +/- WIN lignes, et non la ligne seule : une fiche pose souvent le NOM de l'ability
    # sur une puce et son verdict deux lignes plus bas (mesure : `case-225` §1, ou
    # `SupaCyborkBody` est ligne 61 et « la seed BC courante n'en pose pas » ligne 64 -- le scan
    # mono-ligne ratait EXACTEMENT le verdict faux, en n'attrapant que la phrase juste).
    WIN = 3
    for p in docs:
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = txt.splitlines()
        lines_scanned += len(lines)
        for i, line in enumerate(lines, 1):
            if not ZERO_VERDICT.search(line):
                continue
            verdict_lines += 1
            ctx = "\n".join(lines[max(0, i - 1 - WIN):i + WIN])
            toks = {m.group(1) or m.group(2) for m in TOKEN.finditer(ctx)}
            for t in sorted(x for x in toks if x in known):
                n_all = len(_all_carriers(kits, t))
                n_legacy = len(_legacy_carriers(kits, t))
                if n_all > n_legacy:            # la voie manquante CHANGE le compte
                    rel = p.relative_to(ROOT).as_posix()
                    hits.append((rel, i, t, line.strip()[:150], n_all))
    print("   fiches balayees : %d ; lignes : %d ; lignes portant un verdict « zero » : %d"
          % (len(docs), lines_scanned, verdict_lines))
    print("   CANDIDATS -- verdict « zero » sur une ability dont le compte CHANGE avec les voies "
          "reliques/mythiques : %d" % len(hits))
    for rel, i, t, snippet, n_all in hits:
        print("     %-58s:%-5d %-24s -> %d porteurs" % (rel, i, t, n_all))
        print("        %s" % snippet)
    # Second axe, cible : les fiches qui CITENT `unit_map` ET une ability du gisement.
    print("\n   -- fiches citant `unit_map ... --ability <X>` ou X est du gisement B :")
    n2 = 0
    rx = re.compile(r"unit_map[^\n]{0,80}?--ability\s+`?([A-Za-z0-9_|:]+)`?")
    for p in docs:
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            for m in rx.finditer(line):
                for name in m.group(1).split("|"):
                    if name in gisement:
                        n2 += 1
                        print("     %-58s:%-5d --ability %s (%d porteurs reels)"
                              % (p.relative_to(ROOT).as_posix(), i, name, len(gisement[name])))
    print("     total : %d" % n2)
    return len(hits)


def volet_d(kits: list[dict]) -> None:
    """Effet de bord ASSUME de #323 : les reliques comptent desormais comme modificateurs."""
    print("\n=== VOLET D -- effet de bord : classification `mech` elargie aux voies reliques ===")

    def mech_legacy(k: dict) -> dict:
        m: dict[str, list[str]] = {}
        for aid in (k.get("voies") or {}).get("active", []) + (k.get("voies") or {}).get("passive", []):
            t = UM._abil_text(aid)
            for key, rx in UM.MECH.items():
                if rx.search(t):
                    m.setdefault(key, []).append(aid)
        for tid in k["traits"]:
            t = UM._trait_text(tid)
            for key, rx in UM.MECH.items():
                if rx.search(t):
                    m.setdefault(key, []).append("trait:" + tid)
        return m

    def has_mod(k: dict, m: dict) -> bool:
        if any(m.get(c) for c in ("dmg_bonus", "dmg_reduction", "crit", "block", "evasion",
                                  "extra_hits", "pierce", "shield")):
            return True
        return any(UM.REDUC_TRAIT.search(t) for t in k["traits"])

    before = {k["id"] for k in kits if not has_mod(k, mech_legacy(k))}
    after = {k["id"] for k in kits if not UM._has_dmg_mod(k)}
    lost = sorted(before - after)
    print("   cibles VANILLE avant #323 : %d ; apres : %d ; retirees : %d"
          % (len(before), len(after), len(lost)))
    print("   (une unite retiree portait un modificateur de degat par une voie relique/mythique "
          "-- elle n'a JAMAIS ete une cible vanille)")
    for uid in lost[:40]:
        k = next(x for x in kits if x["id"] == uid)
        print("     %-28s %-7s mech=%s" % (uid, k["kind"], ",".join(k["mech"])))
    if len(lost) > 40:
        print("     ... et %d autres" % (len(lost) - 40))


def volet_e(kits: list[dict], gisement: dict) -> None:
    """Gate de confrontabilite : le pool rate-t-il les reliques de la meme facon ?"""
    print("\n=== VOLET E -- gate de confrontabilite (`rl_duel build --list-pool`) et reliques ===")
    seed_p = ROOT / "data" / "seed-bc.json"
    if not seed_p.exists():
        print("   <data/seed-bc.json absent : non mesure>")
        return
    seed = json.loads(seed_p.read_text(encoding="utf-8"))
    units = seed.get("Units") or []
    equipped = [(u.get("Id"), u.get("TertiaryAbility"), u.get("TertiaryAbilityLevel"))
                for u in units if u.get("TertiaryAbility")]
    print("   seed BC : %d unites, %d avec une relique EQUIPEE (`TertiaryAbility`) : %s"
          % (len(units), len(equipped), equipped))
    eligible = {uid for uid in (u.get("Id") for u in units)
                if uid and (UM._relic_items().get(uid))}
    print("   unites du seed ELIGIBLES a une relique (item.allowedUnits) : %d" % len(eligible))
    print("   -> %d/%d des eligibles l'ont effectivement equipee dans ce seed"
          % (len({e[0] for e in equipped}), len(eligible)))
    pool = _pool()
    if pool is None:
        print("   pool : <non mesure -- --pool non demande, ou la session live n'a pas repondu>")
        return
    print("   pool spawnable : %d unites" % len(pool))
    print("   porteurs ELIGIBLES a une relique ET dans le pool : %d"
          % len(eligible & pool))
    both = sorted({e[0] for e in equipped} & pool)
    print("   porteurs avec relique EQUIPEE ET dans le pool : %s" % (both or "AUCUN"))
    # La ventilation qui TRANCHE : pour chaque ability du gisement, son porteur `lineup` est-il
    # dans le pool ? C'est la difference entre « pas de porteur » (faux) et « porteur present,
    # relique non equipee par ce seed » (vrai, et c'est un montage a faire, pas un mur).
    print("   -- gisement B ventile contre le pool (porteur `lineup` designe) :")
    equipped_names = {e[0] for e in equipped}
    n_pool = n_eq = 0
    for a in sorted(gisement):
        heroes = sorted({uid for uid, kind, _ in gisement[a] if kind == "lineup"})
        inpool = [h for h in heroes if h in pool]
        eq = [h for h in heroes if h in equipped_names]
        n_pool += 1 if inpool else 0
        n_eq += 1 if eq else 0
        print("      %-26s heros=%-46s pool=%-30s equipee=%s"
              % (a, ",".join(heroes)[:46], ",".join(inpool)[:30] or "-", ",".join(eq) or "-"))
    print("   -> %d/%d abilities du gisement ont un porteur `lineup` DANS LE POOL ; "
          "%d l'ont EQUIPEE dans ce seed" % (n_pool, len(gisement), n_eq))


def _pool() -> set | None:
    """Tri-etat (meme discipline que `host_inputs.py`) : None = PAS MESURE, set() = mesure vide."""
    import subprocess
    try:
        r = subprocess.run([sys.executable, str(Path(__file__).with_name("rl_duel.py")),
                            "build", "--list-pool"], capture_output=True, text=True, timeout=240)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    out: set = set()
    for line in (r.stdout or "").splitlines():
        s = line.strip()
        if s and " " not in s and s[0].islower():
            out.add(s)
        m = re.search(r"MoW spawnables : \[(.*)\]", s)
        if m:
            out |= {x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()}
    return out or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", action="store_true",
                    help="volet E : interroge `rl_duel build --list-pool` (RPC, pas de runner)")
    a = ap.parse_args()
    kits = UM.all_kits()
    volet_a(kits)
    gisement = volet_b(kits)
    volet_c(kits, gisement)
    volet_d(kits)
    if a.pool:
        volet_e(kits, gisement)
    else:
        print("\n=== VOLET E -- non demande (relancer avec --pool) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
