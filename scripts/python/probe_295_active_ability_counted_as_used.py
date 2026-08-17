"""Probe #295 -- le COMPARATEUR et le SEUIL d'`IsActiveAbilityCountedAsUsed`, LUS et non deduits.

Question binaire : sur la branche que le port mirroir (`isPreAbilityTrigger = false`), le predicat
natif est-il STRICT (`used > seuil`) ou INCLUSIF (`used >= seuil`) -- et le port l'ecrit-il pareil ?

REPONSE : **STRICT, seuil `Direct(1)`, donc `used > 1`**. Le port ecrivait `used >= 1`, soit UNE
utilisation de retard. Corrige par ce cas.

Le piege est celui de #293, a l'identique : `IdunBattleLogic.Entities.DSLTriggers$$
IsActiveAbilityCountedAsUsed` alloue son trigger par `il2cpp_object_new(<classe>)` puis appelle un
`.ctor` dont le CORPS est trivial (`base..ctor` + deux stores) et donc **DEDUPLIQUE par IL2CPP** :
la table lui donne UN seul proprietaire, qui ne dit RIEN de la classe reellement allouee. La seule
ancre fiable est le POINTEUR DE CLASSE charge juste avant l'allocation. Ici il tombe du bon cote --
la lecture heritee etait juste -- mais elle n'etait pas MESUREE ; elle l'est maintenant.

Ce que ce probe MESURE (offline, aucun runner, aucune session Frida) :

  etape 1  FAMILLE DE CLASSE du sujet, par le pointeur charge (meme mecanique que #293 etape 1,
           reutilisee telle quelle depuis `probe_293_aura_predicate_comparator`).
           Critere : le sujet charge un global propre a la famille STRICTE et AUCUN propre a la
           famille INCLUSIVE.
  etape 2  CORROBORATION par l'encodage : `setg` (strict) dans
           `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger`, `setge`
           (inclusif) dans `...AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger`.
  etape 3  SEUIL, DECOUVERT (aucun offset ecrit en dur) :
             (a) dans le sujet, le `test dl,dl` + `je` qui separe les deux branches donne les DEUX
                 deplacements charges -- celui du fall-through (`isPreAbilityTrigger != 0`) et celui
                 de la cible (`== 0`, la branche mirroree) ;
             (b) dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, la table
                 <deplacement> -> <litteral du noeud constant> ;
             (c) croisement : le seuil de la branche mirroree vaut `Direct(1)`.
  etape 4  ACCORD DU PORT : `COUNTED_AS_USED_THRESHOLD` == le seuil mesure, ET le basculement de
           `is_active_ability_counted_as_used` se fait a `used == seuil + 1` (STRICT) -- pas a
           `used == seuil` (INCLUSIF).
  etape 5  INERTIE, DITE EXPLICITEMENT : `State` n'expose aucun `total_active_ability_used`, donc
           AUCUN test live ne peut couvrir ce seuil. La seule garde est
           `tests/engine/runner/test_active_ability_counted_as_used_offline.py`.

Degradation HONNETE : sans `GameAssembly.dll` du build courant, le probe rend `NON MESURE` et sort
en erreur ; si un decodage d'octets ne rend pas ce qu'il cherche, il le DIT et compte un ecart --
jamais un « 0 ecart » qui se lirait comme un accord.

Usage (depuis scripts/python) :
    python probe_295_active_ability_counted_as_used.py

ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_293_aura_predicate_comparator as P293      # noqa: E402  (Binary/_va2off/_setcc)

# Le sujet. Deux noms selon le build : la classe DSL a ete scindee entre `gqfc5mff6c`
# (`DSLFactory`) et `rnca9r7q6c` (`DSLTriggers` / `DSLFormulas`). On essaie les deux plutot que de
# rendre le probe inutilisable au prochain renommage.
SYMS_SUBJECT = ("IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed",
                "IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed")
SYMS_CONST_CTOR = ("IdunBattleLogic.Entities.DSLFormulas$$.ctor",
                   "IdunBattleLogic.Entities.DSLFactory$$.ctor")

SCAN_BYTES = 0x400            # fenetre de decodage autour d'un point d'interet


# --------------------------------------------------------------------------- outillage octets

def _body(b, sym: str):
    """(va_debut, octets) du corps de `sym`, ou (None, b"") si absent de la table."""
    addrs = b.addrs_of(sym)
    if not addrs:
        return None, b""
    va = addrs[0]
    off = P293._va2off(b.base, b.secs, va)
    if off is None:
        return None, b""
    return va, b.data[off:off + min(b.end_of(va) - va, P293.MAX_FN_BYTES)]


def _first_symbol(b, syms):
    """Le premier symbole de `syms` present dans la table (et son corps)."""
    for s in syms:
        va, buf = _body(b, s)
        if buf:
            return s, va, buf
    return None, None, b""


def _first_load_disp8(buf: bytes, start: int, stop: int):
    """Deplacement du premier `mov r64, [r64 + disp8]` dans `buf[start:stop]`.

    Encodage vise : `REX.W 8B modrm(mod=01, rm != 4/5) disp8` -- exactement la forme d'un
    `champ = objet->+0xNN` a l'endroit qui nous interesse. `rm == 4` (SIB present) est ecarte : ce
    sont les acces a la pile, jamais un champ d'objet ici."""
    i = start
    while i + 4 <= min(stop, len(buf)):
        if 0x48 <= buf[i] <= 0x4F and buf[i + 1] == 0x8B:
            modrm = buf[i + 2]
            if (modrm >> 6) == 1 and (modrm & 7) not in (4,):
                return buf[i + 3], i
        i += 1
    return None, None


def _branch_displacements(buf: bytes):
    """Les deux deplacements charges de part et d'autre du test du booleen `isPreAbilityTrigger`.

    Motif : `84 D2` (`test dl,dl`) suivi d'un `74 rel8` (`je`). Le FALL-THROUGH est la branche
    `isPreAbilityTrigger != 0` ; la CIBLE du saut est la branche `== 0` -- celle que le port
    mirroir. On rend `(disp_pre, disp_non_pre)`, ou `(None, None)` si le motif n'est pas trouve."""
    for i in range(len(buf) - 4):
        if buf[i] == 0x84 and buf[i + 1] == 0xD2 and buf[i + 2] == 0x74:
            rel = buf[i + 3] if buf[i + 3] < 0x80 else buf[i + 3] - 0x100
            fall = i + 4
            tgt = fall + rel
            if not (fall < tgt <= len(buf)):
                continue
            d_pre, _ = _first_load_disp8(buf, fall, tgt)
            d_non, _ = _first_load_disp8(buf, tgt, tgt + SCAN_BYTES)
            if d_pre is not None and d_non is not None and d_pre != d_non:
                return d_pre, d_non
    return None, None


def _const_table(buf: bytes) -> dict:
    """`<deplacement du champ> -> <litteral du noeud constant>` pour le ctor de cache des constantes.

    Le ctor alloue N noeuds constants et les range dans des champs consecutifs. Le litteral part
    dans `edx` (`33 D2` = 0, ou `BA imm32`), le rangement est un `REX.W 89 modrm(mod=01) disp8`.
    On apparie chaque store au DERNIER litteral rencontre avant lui -- l'ordre du code genere, qui
    est aussi celui du source. Decodage LINEAIRE : il peut sur-generer, d'ou le controle de
    plausibilite de l'appelant (table non vide, deplacements croissants, litteraux distincts)."""
    out, last, i = {}, None, 0
    while i + 3 <= len(buf):
        if buf[i] == 0x33 and buf[i + 1] == 0xD2:                      # xor edx,edx
            last, i = 0, i + 2
            continue
        if buf[i] == 0xBA and i + 5 <= len(buf):                       # mov edx, imm32
            last = int.from_bytes(buf[i + 1:i + 5], "little", signed=True)
            i += 5
            continue
        if (0x48 <= buf[i] <= 0x4F and buf[i + 1] == 0x89 and i + 4 <= len(buf)
                and (buf[i + 2] >> 6) == 1 and (buf[i + 2] & 7) not in (4,)):
            if last is not None:
                out.setdefault(buf[i + 3], last)
            i += 4
            continue
        i += 1
    return out


# --------------------------------------------------------------------------- etapes

def step1_class_family(b) -> tuple:
    """Le sujet instancie-t-il la famille STRICTE ou l'INCLUSIVE ? (pointeur de classe)"""
    sym, _, _ = _first_symbol(b, SYMS_SUBJECT)
    if sym is None:
        print("KO etape 1 : aucun symbole sujet dans la table -- rien n'est conclu")
        return 1, None
    incl = set().union(*(b.targets(s) for s in P293.SYMS_INCLUSIVE))
    strict = set().union(*(b.targets(s) for s in P293.SYMS_STRICT))
    only_incl, only_strict = incl - strict, strict - incl
    subj = b.targets(sym)
    hit_incl, hit_strict = subj & only_incl, subj & only_strict
    print(f"etape 1 : {sym}")
    print(f"          globals INCLUSIF-seuls={len(only_incl)} STRICT-seuls={len(only_strict)}"
          f" | sujet touche INCLUSIF={len(hit_incl)} STRICT={len(hit_strict)}")
    bad = 0
    if not hit_strict:
        print("KO etape 1 : le sujet ne charge AUCUN global propre a la famille AmountIsGreater")
        bad += 1
    if hit_incl:
        print("KO etape 1 : le sujet charge un global propre a la famille AmountIsEqualOrGreater"
              " -- le comparateur serait INCLUSIF, la correction #295 est CADUQUE")
        bad += 1
    if not bad:
        print("etape 1 OK : classe de la famille AmountIsGreaterAbilityTrigger -> comparateur"
              " STRICT (minAmount < amount)")
    return bad, sym


def step2_setcc(b) -> int:
    """Corroboration independante : l'encodage du comparateur terminal des deux `ShouldTrigger`."""
    st, si = b.setccs(P293.SYM_ST_STRICT), b.setccs(P293.SYM_ST_INCL)
    print(f"etape 2 : ShouldTrigger STRICT={sorted(st)} | INCLUSIF={sorted(si)}")
    bad = 0
    if not b.addrs_of(P293.SYM_ST_STRICT):
        print("KO etape 2 : AmountIsGreaterAbilityTrigger$$ShouldTrigger absent de la table")
        return 1
    if not (st & {"setl", "setg"}):
        print("KO etape 2 : le ShouldTrigger strict ne porte pas de SETcc strict")
        bad += 1
    if si and st == si:
        print("KO etape 2 : les deux ShouldTrigger portent le MEME comparateur -- ils ne"
              " discriminent plus rien")
        bad += 1
    if not bad:
        print("etape 2 OK : `setg` cote strict, distinct du `setge` inclusif")
    return bad


def step3_threshold(b, sym_subject: str):
    """SEUIL de la branche mirroree (`isPreAbilityTrigger = false`), decouvert -- pas hardcode."""
    _, buf = _body(b, sym_subject)
    d_pre, d_non = _branch_displacements(buf)
    if d_pre is None:
        print("KO etape 3a : motif `test dl,dl` + `je` + deux chargements de champ NON trouve dans"
              " le sujet -- le seuil n'est PAS mesure (aucune conclusion tiree)")
        return 1, None
    sym_ctor, _, cbuf = _first_symbol(b, SYMS_CONST_CTOR)
    if sym_ctor is None:
        print("KO etape 3b : ctor de cache des noeuds constants absent de la table")
        return 1, None
    table = _const_table(cbuf)
    print(f"etape 3a : branche isPreAbilityTrigger!=0 -> champ +{hex(d_pre)} ;"
          f" branche ==0 (mirroree) -> champ +{hex(d_non)}")
    print(f"etape 3b : {sym_ctor} cache "
          + ", ".join(f"+{hex(k)}=Direct({v})" for k, v in sorted(table.items())))
    print("           (decodage LINEAIRE : cette table peut sur-generer sur les champs voisins qui"
          " ne portent pas de noeud constant ; seuls les DEUX champs de l'etape 3a sont croises)")
    bad = 0
    for d, label in ((d_pre, "pre"), (d_non, "non-pre")):
        if d not in table:
            print(f"KO etape 3c : le champ +{hex(d)} (branche {label}) n'est pas dans la table de"
                  f" constantes du ctor -- seuil NON mesure")
            bad += 1
    if bad:
        return bad, None
    seuil = table[d_non]
    print(f"etape 3c OK : seuil de la branche mirroree = Direct({seuil})"
          f" (l'autre branche = Direct({table[d_pre]}))")
    if table[d_pre] >= seuil:
        print("KO etape 3c : la branche `pre` devrait comparer a un seuil STRICTEMENT plus petit"
              " (le compteur n'inclut pas encore l'utilisation courante)")
        bad += 1
    return bad, seuil


def step4_port_agrees(seuil) -> int:
    """Le port ecrit-il le MEME comparateur et le MEME seuil ?"""
    from engine.runner.state import State
    from engine.runner.operations.triggers.loki.fuelled_by_fury import (
        ABILITY_COUNTED_ONCE_PER_BATTLE, COUNTED_AS_USED_THRESHOLD,
        is_active_ability_counted_as_used)

    class _S(State):
        __slots__ = ("_u",)

        def __init__(self, u):
            super().__init__()
            self._u = u

        def total_active_ability_used(self, unit_id, ability_type):
            return self._u

    bad = 0
    if COUNTED_AS_USED_THRESHOLD != seuil:
        print(f"KO etape 4 : COUNTED_AS_USED_THRESHOLD={COUNTED_AS_USED_THRESHOLD} !="
              f" seuil natif Direct({seuil})")
        bad += 1
    ability = sorted(ABILITY_COUNTED_ONCE_PER_BATTLE)[0]
    counted = [u for u in range(seuil + 3)
               if is_active_ability_counted_as_used(_S(u), 1, ability)]
    want = list(range(seuil + 1))            # STRICT : compte tant que used <= seuil
    print(f"etape 4 : ability {hex(ability)} -- used qui COMPTENT = {counted} (attendu {want})")
    if counted != want:
        print("KO etape 4 : le basculement du port n'est pas a used == seuil+1 -> son comparateur"
              " n'est pas STRICT (un `>=` bascule un cran trop tot)")
        bad += 1
    if not bad:
        print(f"etape 4 OK : le port compare `used > {seuil}`, comme le natif")
    return bad


def step5_inert_channel() -> int:
    """L'etat du CANAL -- dit explicitement, pour qu'on ne croie pas ce seuil exerce."""
    from engine.runner.state import State
    live = hasattr(State(), "total_active_ability_used")
    guard = (PYDIR / "tests" / "engine" / "runner"
             / "test_active_ability_counted_as_used_offline.py")
    print(f"etape 5 : canal `State.total_active_ability_used` {'CABLE' if live else 'ABSENT'}"
          f" -> le seuil est {'exerce en bataille' if live else 'INERTE en bataille'}")
    if not guard.is_file():
        print("KO etape 5 : la garde unitaire est absente -- plus RIEN n'exerce ce seuil")
        return 1
    print(f"          seule garde qui l'exerce : {guard.relative_to(PYDIR)}")
    return 0


# --------------------------------------------------------------------------- pilote

def main():
    build = P293._build_hash()
    print(f"build={build}")
    b = P293.Binary(build)                  # leve (NON MESURE) si la DLL du build est absente
    bad, sym = step1_class_family(b)
    bad += step2_setcc(b)
    seuil = None
    if sym is not None:
        d, seuil = step3_threshold(b, sym)
        bad += d
    if seuil is not None:
        bad += step4_port_agrees(seuil)
    else:
        print("etape 4 SAUTEE : seuil non mesure -- l'accord du port n'est PAS etabli")
        bad += 1
    bad += step5_inert_channel()
    print("\nVERDICT:", "OK -- comparateur STRICT, seuil Direct(1), port aligne (`used > 1`)"
          if bad == 0 else f"{bad} ECARTS")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
