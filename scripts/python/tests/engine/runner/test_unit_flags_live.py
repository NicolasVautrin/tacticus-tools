"""O5 — GARDE du canal `combatSnapshot.unitFlags` (`UnitFlagsComponent` exposé live).

CE QUE CE FICHIER VERROUILLE. Avant O5, AUCUN RPC n'exposait les flags d'unité : la face DÉCISION
live devait DÉRIVER `UnitFlag.PreventOverkill` de l'effet 1354 qui le pose. Le gap était nommé
noir sur blanc dans `Scene.prevent_overkill_by_id` et dans `docs/rl/case-195-...`. La dérivation
porte le même invariant — mais c'est une SECONDE expression d'un fait déjà présent tel quel dans
l'ECS, donc un fork de port en puissance : `UnitFlagsComponent.Add` est public, et le jour où un
poseur IMPÉRATIF du flag apparaît, la dérivation par l'effet devient fausse EN SILENCE.

Le hook n'invente rien : il invoque la fonction NOMMÉE que le jeu appelle lui-même,
`IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` (la ligne
`uVar1 = UnitExtensions.HasFlag(defender, 0x13)` d'`ApplyTraitDamageLimitsToDamage`), une fois par
valeur d'enum — valeurs LUES AU RUNTIME (`dumpEnum` sur `IdunBattle.Entities.Enum.UnitFlag`),
jamais recopiées en dur côté hook.

DEUX GARDES, ET LA SECONDE EST CELLE QUI DISCRIMINE VRAIMENT :

 1. ACCORD À TROIS SOURCES — `combatSnapshot.unitFlags`, la dérivation par l'effet actif
    (`effects_prevent_overkill`) et le `preventOverkill` de l'event natif (`result@+0xb3`, #190)
    doivent rendre le MÊME verdict, sur le porteur (`ultraTitus`, VRAI) comme sur le témoin
    (`genesPrimus`, FAUX). C'est ce qui autorise à SUBSTITUER la lecture ECS à la dérivation.

 2. LE CANAL SUIT L'ÉTAT — `UnitFlag.Moved` (=0) sur la MÊME unité, avant puis après un
    `MoveUnitOperation` réel. Sans elle, la garde 1 resterait verte même si `unitFlags` était un
    constat FIGÉ au build : le porteur porte son flag dès le déploiement et ne le lâche jamais, donc
    une table gelée passerait. Ici la même entité change de valeur sous l'effet d'une opération —
    aucune lecture figée ne peut passer.

⚠ `unitFlags = None` (non mesuré) et `[]` (lu, aucun flag) ne sont PAS interchangeables : les
rabattre l'un sur l'autre ferait passer un capteur MORT pour une unité sans flags, et le
consommateur offline (`_prevent_overkill_from_snapshot`) perdrait son repli. La garde 2 tombe
justement sur un `[]` — c'est cette distinction qui la rend lisible.

Montage : `scripts/python/probe_o5_unit_flags.py` ; fixtures : `conftest.py`.
"""
from __future__ import annotations

import probe_o5_unit_flags as O5


# ── 1. ACCORD À TROIS SOURCES ───────────────────────────────────────────────────────────────────

def test_unit_flags_agree_with_effect_derivation_and_native_event(unit_flags_accord_case):
    """Les TROIS sources concordent sur les DEUX cibles, et le couple porteur/témoin produit deux
    valeurs distinctes. Un désaccord ici veut dire que la lecture ECS et la dérivation par l'effet
    ne décrivent PAS le même fait — auquel cas substituer l'une à l'autre serait une régression."""
    m = unit_flags_accord_case()
    ok, why = O5._verdict_accord(m)
    a, b = m.get(O5.CARRIER) or {}, m.get(O5.CONTROL) or {}
    assert a.get("flags_measured") and b.get("flags_measured"), (
        "`unitFlags` non mesuré : le hook ne rend pas le capteur (méthode `HasFlag` irrésolue ou "
        "enum vide) — `None` et `[]` sont distincts exprès, ne pas les confondre")
    assert a.get("src1_snapshot") is True, (
        "`%s` porte `FuelledByFury_BlockOverkill` (flag 0x13) dès le déploiement (#178) : la "
        "lecture ECS doit valoir VRAI. Flags lus : %r" % (O5.CARRIER, a.get("flags")))
    assert b.get("src1_snapshot") is False, (
        "`%s` ne porte pas le flag : la lecture ECS doit valoir FAUX. Flags lus : %r"
        % (O5.CONTROL, b.get("flags")))
    assert ok, why


def test_flag_enum_is_read_at_runtime_and_still_matches_the_table(unit_flags_accord_case):
    """La table `unitFlagTypes` vient de la métadonnée IL2CPP (`dumpEnum`), pas d'une constante du
    dépôt. On la confronte ici à `enums.tsv` : si `UnitFlag` est renuméroté par une mise à jour, ce
    test rougit — au lieu que le port suive silencieusement une numérotation qui a bougé."""
    m = unit_flags_accord_case()
    assert m.get("flag_types_present"), (
        "`unitFlagTypes` absent : le hook n'a pas pu lire l'enum au runtime")
    assert m.get("enum_agrees"), (
        "la table rendue au runtime ne correspond plus à `enums.tsv` (attendus "
        "PreventOverkill=%d, Moved=%d) — `UnitFlag` a été renuméroté"
        % (O5.FLAG_PREVENT_OVERKILL, O5.FLAG_MOVED))


# ── 2. LE CANAL SUIT L'ÉTAT ─────────────────────────────────────────────────────────────────────

def test_moved_flag_flips_on_a_real_move(unit_flags_moved_case):
    """MÊME unité, avant/après un `applyAction` kind=move (seul vecteur qui pose `UnitFlag.Moved`,
    via `IdunBattle.Operations.MoveUnitOperation`). C'est la garde qui distingue un canal VIVANT
    d'une table figée au build."""
    m = unit_flags_moved_case()
    assert not m.get("error"), "montage cassé : %s" % m.get("error")
    assert m.get("move_applied"), (
        "aucune destination adjacente acceptée : le montage n'a plus de variable expérimentale")
    assert m.get("flags_before") is not None, (
        "`unitFlags` non mesuré AVANT le mouvement — `None` (capteur mort) n'est pas `[]` "
        "(lu, aucun flag)")
    assert m.get("moved_before") is False, (
        "l'unité porte déjà `Moved` avant tout mouvement : le montage part d'un état sale "
        "(flags lus : %r)" % (m.get("flags_before"),))
    assert m.get("moved_after") is True, (
        "`Moved` absent APRÈS un `MoveUnitOperation` accepté : le canal ne suit pas l'état, il "
        "rend un constat figé (flags lus : %r)" % (m.get("flags_after"),))
