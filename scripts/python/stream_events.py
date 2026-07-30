#!/usr/bin/env python
"""stream_events — décodage des events StreamDispatcher capturés par applyAction.

Les events bruts (RPC) portent `step` (StepType) et `group` (GroupType) en
ORDINAUX, plus `tags` = Dict<TagKey,int> déjà sérialisé avec les NOMS de TagKey
(StringEnumConverter côté jeu → clés lisibles « Attacker_Id », « Amount »…).
Ici on mappe `step`/`group` → noms depuis la table d'enums, et on labellise
l'effect_type (overwatch / DoT) pour la lecture humaine.

D'OÙ VIENNENT LES ORDINAUX (#254b-a)
------------------------------------
De `data/symbols/<CURRENT>/frida/enums.tsv`, lignes `IdunBattle.Streams.StepType` et
`IdunBattle.Streams.GroupType`. Cette table est **VERSIONNÉE** : elle est donc présente
dans TOUT checkout, y compris un worktree d'agent fraîchement créé.

Ce module lisait auparavant `frida/data/meta/<version>/enums.json`, l'artefact écrit par
le HOST à l'inject (`frida/host/meta-sync.ts::syncEnums`, RPC `dumpEnums`). Or
`frida/data/` est **gitignoré** (`.gitignore:24`) : dans un worktree frais la table était
VIDE, et le premier `python rl_duel.py act ...` levait
`KeyError: StepType.UnitDamaged absent de enums.json` — **après** que le RPC `applyAction`
ait appliqué l'action. Piège double, mesuré le 2026-07-30 : la commande « échoue » alors
que l'état du runner A BOUGÉ, et le message accuse une renumérotation d'enum alors que la
cause est un fichier absent.

Pourquoi la table versionnée et pas l'artefact host (arbitrage MESURÉ, cf. `case-254bis`) :

* **équivalence** : sur `rnca9r7q6c`, `enums.tsv` et `frida/data/meta/1.41.128/enums.json`
  donnent EXACTEMENT le même contenu — StepType 62/62 et GroupType 104/104 membres, zéro
  ordinal divergent. Changer de source ne change donc aucune valeur décodée.
* **péremption détectable** : `enums.tsv` porte une estampille
  `#!il2cpp-provenance sha256=… build=…` et l'axe 1 de `scripts/python/symbols_sync.py`
  la compare au `GameAssembly.dll` INSTALLÉ (fail-closed). L'artefact host, lui, n'a
  aucune estampille, est indexé par version de JEU (« 1.41.128 ») et non par hash de
  BUILD, et était choisi par simple tri de version — une table périmée y mentait en
  silence, ce qui est exactement le motif #251/#252.
* **pas de session requise** : le décodage d'un compte rendu ne doit pas dépendre d'un
  host vivant + d'un RPC. Régénérer à la volée aurait ajouté « host éteint » comme second
  mode de panne d'un chemin purement local.

Le coût accepté : la table doit être re-dérivée à chaque changement de build. Il est
DÉJÀ payé — tout le dépôt en dépend (`catalog_inject.enum_map`, `targeting_rule.py`,
`active_ability_type.py`, …) — et il est GARDÉ (`symbols_sync.py`).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from symbols_layout import LayoutError, build_dir

# Les enums de la couche stream, cités par leur nom PLEINEMENT QUALIFIÉ (c'est la clé
# de `enums.tsv`, et c'est aussi le symbole natif — `IdunBattle.Streams.StreamDispatcher$$Action`
# prend un `StepType` en 1er argument).
STEP_ENUM = "IdunBattle.Streams.StepType"
GROUP_ENUM = "IdunBattle.Streams.GroupType"

_REGEN = (
    "  Regenerer la table : python scripts/python/dump_il2cpp.py\n"
    "                  puis python scripts/python/preprocess_il2cpp_dump.py\n"
    "  Verifier build installe <-> table : python scripts/python/symbols_sync.py")


class EnumTableUnavailable(RuntimeError):
    """La table d'enums versionnee est absente/incomplete -- toujours bloquant.

    NOMME le fichier attendu et la commande qui le regenere : un `KeyError` nu sur un
    membre d'enum envoie chercher une renumerotation de build alors que la cause peut
    etre un simple fichier manquant (c'est ce qui a coute du temps le 2026-07-30)."""


# Effect_Type tags (cf. project_effect_type_attribution, confirmé live).
# L'overwatch n'est PAS un cas spécial : c'est un UnitDamaged avec ce tag, au
# même titre que le DoT. On se contente de LABELLISER l'effect_type pour la
# lecture humaine — la classification se fait par direction (subi / infligé).
OVERWATCH_EFFECT_TYPE = 1009
DOT_EFFECT_TYPE = 5
EFFECT_TYPE_NAMES = {OVERWATCH_EFFECT_TYPE: "overwatch", DOT_EFFECT_TYPE: "dot"}


def effect_label(et) -> str | None:
    """Nom lisible d'un Effect_Type (overwatch/dot), sinon None."""
    return EFFECT_TYPE_NAMES.get(et) if et else None


@lru_cache(maxsize=1)
def source_path() -> Path:
    """Le fichier d'ou sortent les ordinaux. Erreur DURE si `data/symbols/` est
    inexploitable -- on ne devine pas le build (cf. `symbols_layout`)."""
    try:
        return build_dir() / "frida" / "enums.tsv"
    except LayoutError as e:
        raise EnumTableUnavailable(
            "table d'enums introuvable -- data/symbols inexploitable :\n  %s\n%s"
            % (e, _REGEN)) from e


@lru_cache(maxsize=8)
def _par_nom(enum_fq: str) -> dict:
    """{MEMBRE: ordinal} d'un enum, lu dans `data/symbols/<CURRENT>/frida/enums.tsv`.

    Format d'une ligne : `<nom pleinement qualifie>\\t<ord>=<MEMBRE>,<ord>=<MEMBRE>,...`
    (produit par `preprocess_il2cpp_dump.py`, 1re ligne = estampille de provenance)."""
    p = source_path()
    if not p.is_file():
        raise EnumTableUnavailable(
            "table d'enums ABSENTE : %s\n"
            "  Les ordinaux StepType/GroupType viennent de cette table VERSIONNEE, pas de\n"
            "  l'artefact host frida/data/meta/<version>/enums.json (gitignore).\n%s"
            % (p.as_posix(), _REGEN))
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.startswith(enum_fq + "\t"):
                continue
            out = {}
            for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                ordinal, membre = kv.split("=", 1)
                out[membre] = int(ordinal)
            return out
    raise EnumTableUnavailable(
        "enum %r absent de %s -- l'enum a-t-il ete renomme/retire par la MAJ du jeu, ou la\n"
        "  table est-elle tronquee ?\n%s" % (enum_fq, p.as_posix(), _REGEN))


# La table est indexee PAR NOM (`{MEMBRE: ordinal}`) ; `step_name`/`group_name` ont besoin
# de l'INVERSE. L'ancienne version interrogeait la map par ID sans l'inverser, donc ne
# trouvait JAMAIS rien et rendait toujours `Step#N` / `Group#N` : panne muette, le repli
# avait exactement la forme d'un ordinal inconnu.
@lru_cache(maxsize=1)
def _step_par_nom() -> dict:
    return _par_nom(STEP_ENUM)


@lru_cache(maxsize=1)
def _group_par_nom() -> dict:
    return _par_nom(GROUP_ENUM)


def _inverse(par_nom: dict) -> dict:
    out = {}
    for nom, val in par_nom.items():
        try:
            out[int(val)] = nom
        except (TypeError, ValueError):
            continue
    return out


@lru_cache(maxsize=1)
def _step_map() -> dict:
    """id -> NOM."""
    return _inverse(_step_par_nom())


@lru_cache(maxsize=1)
def _group_map() -> dict:
    """id -> NOM."""
    return _inverse(_group_par_nom())


def step_name(i) -> str:
    return _step_map().get(int(i), f"Step#{i}") if i is not None else "Step#None"


def group_name(i) -> str:
    return _group_map().get(int(i), f"Group#{i}") if i is not None else "Group#None"


@lru_cache(maxsize=None)
def step_id(nom: str) -> int:
    """Ordinal de `StepType.<nom>` SUR LE BUILD COURANT.

    ⚠ NE JAMAIS figer un ordinal de `StepType` en dur. Ces valeurs sont IMPLICITES : le retrait
    d'un membre au milieu decale tout ce qui suit. Mesure du 2026-07-29 -- `rnca9r7q6c` a retire
    `RestoreArmorInfo` (7), donc `RemoveUnit` est passe de 12 a 11 et `ReceiveEffect` de 16 a 15.
    Les deux ordinaux etaient ecrits en dur ici : `deaths` comptait des `ChangeStats` et `effects`
    des `LoseEffect`, SANS ERREUR NI TRACE -- et `analyze()` alimente `rl_duel.py` et
    `rl_probe_step.py`.

    Leve si le nom n'existe plus : un membre disparu doit CASSER, pas se replier silencieusement
    sur un ordinal qui appartient desormais a un autre pas. Une table absente leve, elle, un
    `EnumTableUnavailable` DISTINCT qui nomme le fichier -- les deux causes ne doivent pas porter
    le meme message (c'est ce qui a envoye chercher une renumerotation pour un fichier manquant)."""
    v = _step_par_nom().get(nom)
    if v is None:
        # `as_posix()` : `str(KeyError)` passe par `repr` de l'argument, qui DOUBLE les
        # antislashs -- un chemin Windows y devient illisible et non copiable.
        raise KeyError(
            "StepType.%s absent de %s -- le pas a-t-il ete renomme ou retire par la MAJ du jeu ?"
            % (nom, source_path().as_posix()))
    return int(v)


def _tags(ev: dict) -> dict:
    t = ev.get("tags")
    if not t:
        return {}
    try:
        return json.loads(t) if isinstance(t, str) else dict(t)
    except (ValueError, TypeError):
        return {}


def decode_event(ev: dict) -> str:
    """Une ligne lisible pour un event (group ouvrant / action / group fermant),
    avec indentation par profondeur de scope (suivie par le caller)."""
    k = ev.get("kind")
    if k == "group":
        src = ev.get("source")
        return (f"[{group_name(ev.get('group'))} e={ev.get('entity')}"
                + (f" «{src}»" if src else "") + "]")
    if k == "finish":
        return "[/]"
    tags = _tags(ev)
    tg = " ".join(f"{kk}={vv}" for kk, vv in tags.items())
    return (f"{step_name(ev.get('step'))} e={ev.get('entity')}"
            + (f"  {tg}" if tg else ""))


def decode_lines(events: list, max_lines: int = 60) -> list[str]:
    """Cascade décodée + indentée par nesting de groupes (group ouvre, /  ferme)."""
    out: list[str] = []
    depth = 0
    for ev in (events or [])[:max_lines]:
        k = ev.get("kind")
        if k == "finish":
            depth = max(0, depth - 1)
            out.append("  " * depth + decode_event(ev))
        elif k == "group":
            out.append("  " * depth + decode_event(ev))
            depth += 1
        else:
            out.append("  " * depth + decode_event(ev))
    if events and len(events) > max_lines:
        out.append(f"… (+{len(events) - max_lines} events)")
    return out


def analyze(events: list, my_ids) -> dict:
    """Décode la cascade UNIFORMÉMENT — aucun cas spécial overwatch : c'est un
    UnitDamaged taggé Effect_Type=1009 comme un autre, on le classe par DIRECTION
    et on labellise son effet. my_ids = squadId que JE contrôle.
      - damage   : toutes les UnitDamaged (attacker/target/amount/crit/killed/effect)
      - received : dégâts SUBIS par mes units (target∈moi, attacker∉moi) — inclut
                   l'attaque adverse ET les réactions (overwatch/counter/aura via
                   `effect`). DoT-sur-moi (attacker absent/None) compte aussi.
      - dealt    : dégâts que J'INFLIGE (attacker∈moi) — pendant le tour adverse,
                   c'est ma riposte/overwatch/aura (chacun avec son `effect`).
      - deaths   : entités retirées (RemoveUnit)
      - effects  : Effect_Id reçus (ReceiveEffect)
    `effect` = label de l'Effect_Type (overwatch/dot/None)."""
    my = set(my_ids or [])
    out = {"damage": [], "received": [], "dealt": [],
           "deaths": [], "effects": []}
    # Pile de GROUPES (suivie en marchant la cascade) : c'est le signal qui
    # distingue une attaque MANUELLE (sous un groupe `User_*` = activation
    # commandée) d'une attaque AUTO/PASSIVE (StartTurn, triggered, riposte…).
    # Ex. Kharn = 4 hits sous `StartTurn` (auto TheBetrayer) + 4 sous
    # `User_UseAbility` (manuel) — sans ça on ne voyait pas le « auto + manuel ».
    stack: list[str] = []
    for ev in events or []:
        k = ev.get("kind")
        if k == "group":
            stack.append(group_name(ev.get("group")))
            continue
        if k == "finish":
            if stack:
                stack.pop()
            continue
        if k != "action":
            continue
        step = ev.get("step")
        tags = _tags(ev)
        if step == step_id("UnitDamaged"):   # événement uniforme
            atk, tgt = tags.get("Attacker_Id"), tags.get("Target_Id")
            manual = any(g.startswith("User_") for g in stack)
            d = {
                "attacker": atk, "target": tgt,
                "amount": tags.get("Amount"),
                "crit": bool(tags.get("Attack_DidCrit")),
                "killed": bool(tags.get("Attack_WasMemberKilled")),
                "ability": tags.get("Active_Ability_Type"),
                "effect_type": tags.get("Effect_Type"),
                "effect": effect_label(tags.get("Effect_Type")),
                # auto/passif = hors activation commandée (StartTurn auto de
                # TheBetrayer, triggered, riposte…). group = groupe englobant
                # le plus externe (StartTurn / User_UseAbility / …).
                "auto": not manual,
                "group": stack[0] if stack else None,
            }
            out["damage"].append(d)
            if atk in my:
                out["dealt"].append(d)
            elif tgt in my:
                out["received"].append(d)
        elif step == step_id("RemoveUnit"):
            out["deaths"].append(ev.get("entity"))
        elif step == step_id("ReceiveEffect"):
            out["effects"].append(tags.get("Effect_Id"))
    return out


if __name__ == "__main__":
    # Smoke test : ALLER-RETOUR par NOM, jamais un ordinal fige.
    # L'ancienne version assertait `step_name(4) == "UnitDamaged"` et trois autres ordinaux en
    # dur. Elle etait DOUBLEMENT fausse : `step_name` rendait toujours `Step#N` (map interrogee
    # a l'envers), donc ce smoke test n'a jamais pu passer -- il n'etait donc jamais joue. Et
    # asserter un ordinal, c'est re-armer exactement le piege qu'on vient de desamorcer.
    print("source : %s" % source_path())
    assert _step_map(), "StepType vide"
    assert _group_map(), "GroupType vide"
    for nom in ("UnitDamaged", "RemoveUnit", "ReceiveEffect", "ChangePosition"):
        i = step_id(nom)
        assert step_name(i) == nom, "aller-retour casse : %s -> %d -> %s" % (nom, i, step_name(i))
    try:
        step_id("RestoreArmorInfo")
    except KeyError:
        pass                       # retire par rnca9r7q6c : l'absence DOIT lever
    else:
        print("NOTE : RestoreArmorInfo est revenu -- les ordinaux ont pu re-decaler.")
    print("stream_events OK -- StepType(%d) GroupType(%d) ; UnitDamaged=%d RemoveUnit=%d "
          "ReceiveEffect=%d" % (len(_step_map()), len(_group_map()), step_id("UnitDamaged"),
                                step_id("RemoveUnit"), step_id("ReceiveEffect")))
