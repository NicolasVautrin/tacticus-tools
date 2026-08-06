"""#437-r1-r1-r1 -- LA FACE D'UN `EffectBonus` EST LE SLOT VIRTUEL PAR LEQUEL IL SORT.

CE QUE CE PROBE MESURE, ET POURQUOI CE N'EST PAS UNE DEDUCTION
--------------------------------------------------------------
#586 a laisse ouvert : « il faut MESURER la face de chaque effet, pas la DEDUIRE du porteur ».
Deduire du PORTEUR est effectivement faux (`Terrifying_ExtraDefense` est porte par la CIBLE et
atterrit dans l'accumulateur ATTAQUANT). Mais la face n'est pas pour autant une propriete
inobservable : elle se LIT, exhaustivement et hors-ligne, dans la structure de classes du binaire.

`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` et
`...$$CalculateDefenderModifiersForPrediction` ont, au decompile (`rnca9r7q6c`), la MEME forme :

    acc = DamageModifiers.Empty()
    <fold des stat-mods de SA face> -> DamageModifiers$$Add(acc, modifier)      # surcharge 1-ARG
    foreach (entree du MEME dictionnaire d'effets)                             # 5e argument
        foreach (effet de l'entree)
            b = effet.<SON slot>(abilityEntities)                              # cf. ci-dessous
            if (b.HasValue) liste.Add(b.Value)
    foreach (damageBonus in liste)
        modifier = damageBonus.@0x48.HasValue
                 ? GetFloatMultiplierFromPercentage(@0x48) : null
        DamageModifiers$$Add(acc, damageBonus, modifier)                       # surcharge 2-ARGS

Les DEUX builders enumerent le MEME dictionnaire d'effets (celui de la bataille, pas « ceux du
porteur ») ; ce qui les separe est le SLOT invoque : 0x16/0x17 pour l'attaquant, 0x1a/0x1b pour le
defenseur. Le pourcentage part donc dans `Multiplier@0x30` de l'accumulateur de CE builder-la, et
`CalculateBaseDamageWithAllModifiers` arrondit une fois par accumulateur non nul (la loi #437-r1-r1).

=> **La face d'un effet est le slot qu'il IMPLEMENTE**, jamais l'unite qui le porte. Le trigger
(`OwnerIsTarget` / `OwnerIsCaster` / `OwnerIsActor`) choisit QUELLE unite le declenche ; il ne
choisit PAS l'accumulateur.

DEUX FAMILLES DE FORWARDER, lues au decompile :
  * `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`
    est un forwarder NU vers le slot virtuel `CreateDamageModifier` de la sous-classe (relu :
    il recopie les 0x58 octets du `Nullable<EffectBonus>` rendu, sans rien d'autre). Toute classe
    derivant de `DamageModifierAbilityEffect` est donc vue par le builder ATTAQUANT.
  * symetriquement `ADamageDefenseModifierAbilityEffect` / `CreateDamageDefenseModifier` ->
    builder DEFENSEUR.

DEUX SOURCES INDEPENDANTES, et elles concordent EXACTEMENT (2026-08-04, `rnca9r7q6c`) :
  `frida/classes.tsv` (dump IL2CPP des `Il2CppClass` reels) : 19 filles de
  `DamageModifierAbilityEffect`, 14 de `ADamageDefenseModifierAbilityEffect` ;
  `frida/methods.tsv` : 19 `CreateDamageModifier`, 14 `CreateDamageDefenseModifier`.

CE QUE LE PROBE REND
--------------------
La table `effet du port -> classe native -> face NATIVE -> face du PORT`, et le compte des
DIVERGENCES. `rc` = nombre de divergences (0 = le port attribue les faces comme le natif).
Un effet dont la classe native ne se resout pas est compte a part et IMPRIME -- jamais avale.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

REPO = _HERE.parents[1]
SYMBOLS = REPO / "data" / "symbols"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 105 fichiers, dont `data/seed-bc.json` (cascade d'import) et les DEUX tables
#: `data/symbols/<build>/frida/{classes,methods}.tsv`.
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py", "data/seed-bc.json"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte DEUX cotes. Cote NATIF : la chaine de parents de `classes.tsv` et "
              "la classe declarante de `methods.tsv` -- donc un changement de build peut "
              "renverser un verdict SANS qu'une ligne du depot bouge (`build: True`). Cote "
              "PORT : le SOURCE des classes d'effet, lu par `inspect` apres import, donc la "
              "fermeture d'import de `PORT_CHANNELS` -- prise a tout `scripts/python/**`.",
}

#: Slot natif -> accumulateur. Les deux premiers sont les slots INVOQUES par les builders ; les
#: deux derniers sont les abstraits que les forwarders de famille delegent.
SLOT_FACE = {
    "CreateEffectDamageBonusForAttack": "attacker",     # slot 0x16, builder ATTAQUANT
    "CreateDamageModifier": "attacker",                 # via DamageModifierAbilityEffect
    "CreateEffectDamageMalusForDefense": "defender",    # slot 0x1a, builder DEFENSEUR
    "CreateDamageDefenseModifier": "defender",          # via ADamageDefenseModifierAbilityEffect
}
#: Les deux bases dont le forwarder decide la face de TOUTE la descendance.
FORWARDER_FACE = {
    "IdunBattle.Entities.Effects.DamageModifierAbilityEffect": "attacker",
    "IdunBattle.Entities.Effects.ADamageDefenseModifierAbilityEffect": "defender",
}

#: CANAUX DU PORT qui produisent un `EffectBonus` de DEGAT, et l'accumulateur ou leur agregateur
#: le verse AUJOURD'HUI. Il y en a CINQ, pas deux -- les trois canaux AURA mirroirent la boucle
#: state-wide `EffectWithTarget` des MEMES deux builders natifs, et un effet-aura a donc une face
#: exactement comme les autres. Les omettre laisserait un tiers du gisement hors table.
#:   `<methode du port>`: (`face par defaut de son agregateur`, `attribut de derogation`)
PORT_CHANNELS = {
    "create_effect_damage_bonus_for_attack": ("attacker", "ATTACK_BONUS_NATIVE_FACE"),
    "create_effect_damage_malus_for_defense": ("defender", "DEFENSE_MALUS_NATIVE_FACE"),
    "create_aura_attack_damage_bonus_for_ally": ("attacker", "AURA_ATTACK_BONUS_NATIVE_FACE"),
    "create_aura_attack_damage_malus_for_enemy": ("attacker", "AURA_ATTACK_MALUS_NATIVE_FACE"),
    "create_aura_defense_damage_malus_for_ally": ("defender", "AURA_DEFENSE_MALUS_NATIVE_FACE"),
}

#: Citation d'un symbole natif d'effet dans le source du port.
#: ⚠ Les `\s*` ne sont pas de la tolerance decorative : le depot ECRIT ses symboles sur plusieurs
#: lignes quand ils depassent la colonne (ex. `...Loki.PrimarchOfTheFirstLegion_ExtraDmgEffect$$`
#: puis `CreateEffectDamageBonusForAttack` a la ligne suivante). Sans eux, la citation la plus
#: LONGUE -- donc la plus susceptible d'etre coupee -- est precisement celle qu'on rate, et
#: l'effet retombe en « NATIF NON RESOLU » alors que son symbole est ecrit noir sur blanc.
#: Le faux positif est impossible : tout candidat est CONFRONTE a `classes.tsv`.
_SYM = re.compile(r"IdunBattle\.\s*Entities\.\s*Effects\.\s*(?:Loki\.\s*)?(\w+)\s*\$\$\s*Create"
                  r"(?:EffectDamage(?:BonusForAttack|MalusForDefense)|Damage(?:Defense)?Modifier)")


def _build_dir() -> Path:
    """Repertoire `data/symbols/<build>` le plus recent qui porte les DEUX tables utiles."""
    cands = sorted(p.parent.parent for p in SYMBOLS.glob("*/frida/classes.tsv")
                   if (p.parent / "methods.tsv").exists())
    if not cands:
        raise SystemExit("[437r1r1r1] data/symbols/<build>/frida/{classes,methods}.tsv introuvable")
    return cands[-1]


def native_face_index(build: Path):
    """`{nom court de classe native: (face, comment elle a ete etablie)}`, DEUX sources.

    (a) `classes.tsv` : la chaine de parents. Une classe qui descend d'un des deux forwarders
        herite de SA face -- c'est vrai meme si son propre corps a ete deduplique.
    (b) `methods.tsv` : la classe DECLARANTE de chaque implementation de slot. C'est la source
        des classes qui derivent directement de `BaseEffect` et surchargent un slot en propre.

    Les deux sont conservees separement pour que le desaccord soit VISIBLE (`--audit`) : un
    garde-fou dont les deux sources sont fondues ne peut plus signaler sa propre panne.
    """
    parent = {}
    for line in (build / "frida" / "classes.tsv").read_text(encoding="utf-8",
                                                            errors="replace").splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0]:
            parent[parts[0]] = parts[2]

    by_chain = {}
    for cls in parent:
        seen, cur = 0, cls
        while cur and seen < 12:
            face = FORWARDER_FACE.get(cur)
            if face is not None:
                by_chain[cls.rsplit(".", 1)[-1]] = face
                break
            cur = parent.get(cur)
            seen += 1

    by_method = {}
    for line in (build / "frida" / "methods.tsv").read_text(encoding="utf-8",
                                                            errors="replace").splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        meth = parts[1].rsplit(".", 1)[-1]
        face = SLOT_FACE.get(meth)
        if face is None:
            continue
        short = parts[2].rsplit(".", 1)[-1]
        by_method.setdefault(short, set()).add(face)
    return parent, by_chain, by_method


def resolve_native_class(port_cls, parent) -> tuple[str | None, str]:
    """Classe NATIVE d'une classe d'effet du port, et par quelle voie elle a ete etablie.

    Voie 1 (la seule qui n'invente rien) : le SYMBOLE cite verbatim dans le source de la classe
    du port -- convention du depot (« on cite un SYMBOLE, jamais une adresse »).
    Voie 2 : le nom, `<EffetX>Effect` / `<EffetX>_Effect`, CONFRONTE a `classes.tsv` (une classe
    qui n'y existe pas n'est pas retenue).
    """
    short_names = {c.rsplit(".", 1)[-1] for c in parent}
    # ⚠ On remonte la MRO du port : une sous-classe de PORT (`...DroneEffect(...Effect)`) mirroire la
    # MEME classe NATIVE que son parent -- `isDrone` est un champ d'instance, pas une autre classe --
    # et ne re-cite pas le symbole. Sans cette remontee elle sort « NATIF NON RESOLU » a tort.
    for cls in port_cls.__mro__:
        try:
            src = inspect.getsource(cls)
        except (OSError, TypeError):
            continue
        cited = [m for m in _SYM.findall(src) if m in short_names]
        if cited:
            # La classe CITEE le plus souvent dans ce corps ; egalite -> la premiere.
            best = max(set(cited), key=lambda n: (cited.count(n), -cited.index(n)))
            return best, ("symbole cite" if cls is port_cls else "symbole cite (parent port)")
    return None, "-"


def resolve_by_name(effect_name: str, parent) -> str | None:
    short_names = {c.rsplit(".", 1)[-1] for c in parent}
    for cand in (effect_name + "Effect", effect_name + "_Effect", effect_name):
        if cand in short_names:
            return cand
    return None


def port_faces(cls, base):
    """Faces que le PORT donne aux contributions de cette classe, telles qu'elles ATTERRISSENT
    (defaut du canal, ou derogation posee sur la classe)."""
    out = set()
    for meth, (default, attr) in PORT_CHANNELS.items():
        if getattr(cls, meth) is not getattr(base, meth):
            out.add(getattr(cls, attr, default))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="table effet -> face NATIVE vs face du PORT")
    ap.add_argument("--audit", action="store_true",
                    help="imprime aussi le desaccord entre les deux sources natives")
    args = ap.parse_args()

    build = _build_dir()
    parent, by_chain, by_method = native_face_index(build)

    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import EFFECT_CLASSES

    print("[437r1r1r1] tables : %s" % (build / "frida"))
    print("[437r1r1r1] familles de forwarder : %d filles attaquantes, %d defenseuses"
          % (sum(1 for f in by_chain.values() if f == "attacker"),
             sum(1 for f in by_chain.values() if f == "defender")))

    if args.audit:
        desacc = [(c, by_chain[c], sorted(by_method[c]))
                  for c in sorted(set(by_chain) & set(by_method))
                  if by_method[c] != {by_chain[c]}]
        print("[audit] classes ou chaine-de-parents et methodes-declarees divergent : %d"
              % len(desacc))
        for c, a, b in desacc:
            print("  %-56s chaine=%s  methodes=%s" % (c, a, b))

    rows, unresolved, divergent = [], [], []
    for name, cls in sorted(EFFECT_CLASSES.items()):
        pf = port_faces(cls, BaseEffect)
        if not pf:
            continue
        nc, how = resolve_native_class(cls, parent)
        if nc is None:
            nc, how = resolve_by_name(name, parent), "nom"
        nf = set()
        if nc:
            if nc in by_chain:
                nf.add(by_chain[nc])
            nf |= by_method.get(nc, set())
        rows.append((name, cls.__name__, sorted(pf), nc or "-", sorted(nf), how))
        if not nf:
            unresolved.append(name)
        elif nf != pf:
            divergent.append((name, sorted(pf), sorted(nf)))

    print()
    print("%-44s %-40s %-18s %-44s %s"
          % ("EFFET (port)", "classe du port", "PORT", "classe native", "NATIF"))
    for name, pcls, pf, nc, nf, how in rows:
        flag = ""
        if not nf:
            flag = "   <<< NATIF NON RESOLU (%s)" % how
        elif set(nf) != set(pf):
            flag = "   <<< DIVERGENCE"
        print("%-44s %-40s %-18s %-44s %-18s%s"
              % (name, pcls, "+".join(pf), nc, "+".join(nf), flag))

    print()
    print("classes du port a face de degat : %d" % len(rows))
    print("natif non resolu                : %d  %s"
          % (len(unresolved), unresolved if unresolved else ""))
    print("DIVERGENCES                     : %d" % len(divergent))
    for name, pf, nf in divergent:
        print("  %-44s port=%-18s natif=%s" % (name, "+".join(pf), "+".join(nf)))
    rc = len(divergent) + len(unresolved)
    print("VERDICT: %s (rc=%d)" % ("PASS" if rc == 0 else "FAIL", rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
