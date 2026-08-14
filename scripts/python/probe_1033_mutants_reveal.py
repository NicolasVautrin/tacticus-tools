"""#1033 -- MUTATION ADVERSARIALE de mes propres gardes.

Chaque mutant casse UN etage du port ; on exige que `test_1033_reveal_offline.py` ROUGISSE, et on
imprime le premier message d'assertion. Un mutant qui laisse la banque VERTE est une garde qui ne
garde rien.
"""
import io, os, re, shutil, subprocess, sys

# L'arbre temoin est CELUI OU L'ON TOURNE, derive par git -- jamais un chemin en dur.
# Il portait `...\.claude\worktrees\agent-a78308fc7b47d1544`, le worktree de l'agent qui a
# ecrit ce probe : disparu avec lui, donc `git archive` rendait un tar VIDE et les mutants
# ne mesuraient plus rien. `probe_273 --only-scan` le rougissait sur `master`.
W = subprocess.run(
    ["git", "-C", os.path.dirname(os.path.abspath(__file__)), "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, check=True).stdout.strip()
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mut_a78308")
TEST = "tests/engine/runner/test_1033_reveal_offline.py"

#: (libelle, fichier relatif, motif LU, remplacement) -- chaque mutation est une faute PLAUSIBLE.
MUTANTS = [
    ("M1 masque : on prend le litteral du ctor au lieu de l'UNION avec le preset",
     "engine/runner/abilities/loki/reveal.py",
     "rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy\n                  "
     "| TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls)",
     "rules=int(TR.TargetMatchesDynamicRule\n                  "
     "| TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls)"),

    ("M2 arbre : la source devient la CIBLE (confusion Caster@+0x48 / Target@+0x60)",
     "engine/runner/abilities/loki/reveal.py",
     "source_ref=Caster(),                       # source = Caster@+0x48",
     "source_ref=Target(),                       # MUTANT"),

    ("M3 arbre : duree en dur au lieu du gameconfig",
     "engine/runner/abilities/loki/reveal.py",
     "duration_rounds=rounds,                    # TurnsFromRounds(nrOfRounds)",
     "duration_rounds=1,                         # MUTANT"),

    ("M4 gate : le conjoint HasFaction(Aeldari) est oublie",
     "engine/runner/abilities/loki/reveal.py",
     "            if _faction(uc.visual_id) != AELDARI_FACTION:      # `HasFaction(unit, 8 = Aeldari)`\n"
     "                continue\n",
     ""),

    ("M5 gate : le conjoint IsFriend(caster) est oublie",
     "engine/runner/abilities/loki/reveal.py",
     "            if not units_are_friends(state, uid, caster_id):   # `IsFriend(unit, caster, entities)`\n"
     "                continue\n",
     ""),

    ("M6 gate : on ignore QUI a tue (le KillerId n'est plus compare)",
     "engine/runner/abilities/loki/reveal.py",
     "            if int(ds[0]) != int(killer_id):                   # `get_KillerId(ds) == killer.Id`\n"
     "                continue\n",
     ""),

    ("M7 gate : une cible DEJA Revealed est acceptee (HasEffect oublie)",
     "engine/runner/abilities/loki/reveal.py",
     "        if has_effect_of_type(state, int(target_id), REVEALED):\n"
     "            return int(TR.TargetMatchesDynamicRule)\n",
     ""),

    ("M8 effet : le tri-etat devient une inimitie SUPPOSEE (None -> ennemi)",
     "engine/entities/effects/loki/revealed.py",
     "        if owner_team is None or actor_team is None:      # non mesure -> gate FERME\n"
     "            return None\n",
     ""),

    ("M9 effet : la magnitude est lue comme une VARIABLE par niveau",
     "engine/entities/effects/loki/revealed.py",
     "return ability_var(ABILITY_ID, AbilityConstantType.extraDmgPct.name, is_constant=True)",
     "return ability_var(ABILITY_ID, AbilityConstantType.extraDmgPct.name, is_constant=False)"),

    ("M10 effet : on recopie la FACE du voisin de forme (Markerlight -> attacker)",
     "engine/entities/effects/loki/revealed.py",
     "    # `Fix64.Round` appliques.\n",
     "    # `Fix64.Round` appliques.\n    DEFENSE_MALUS_NATIVE_FACE = \"attacker\"\n"),

    ("M11 AUDIT : retour au comportement d'AVANT (un nom hors enum = un no-op)",
     "audit_combat_ability_coverage.py",
     "        if aid is None:",
     "        if False:"),

    ("M12 AUDIT : le predicat de portage redevient une LISTE BLANCHE (ABILITY_TRIGGERS seul)",
     "audit_combat_ability_coverage.py",
     "    for attr in sorted(dir(REG)):\n        if not attr.isupper():\n            continue\n"
     "        d = getattr(REG, attr)\n        if isinstance(d, dict) and d.get(nm):\n"
     "            return attr\n    return None",
     "    return \"ABILITY_TRIGGERS\" if REG.ABILITY_TRIGGERS.get(nm) else None"),
]


def arbre_frais():
    if os.path.isdir(BASE):
        shutil.rmtree(BASE, ignore_errors=True)
    os.makedirs(BASE, exist_ok=True)
    tar = subprocess.run(["git", "-C", W, "archive", "HEAD"], capture_output=True)
    p = subprocess.Popen(["tar", "-x", "-C", BASE], stdin=subprocess.PIPE)
    p.communicate(tar.stdout)
    return os.path.join(BASE, "scripts", "python")


def main():
    ok = True
    for libelle, rel, motif, repl in MUTANTS:
        py = arbre_frais()
        cible = os.path.join(py, rel.replace("/", os.sep))
        with io.open(cible, "r", encoding="utf-8") as f:
            src = f.read()
        if motif not in src:
            print("!! %s -- MOTIF INTROUVABLE dans %s : le mutant ne mute RIEN" % (libelle, rel))
            ok = False
            continue
        with io.open(cible, "w", encoding="utf-8") as f:
            f.write(src.replace(motif, repl, 1))
        r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-x"],
                           cwd=py, capture_output=True, text=True)
        rouge = r.returncode != 0
        msg = ""
        for ligne in (r.stdout or "").splitlines():
            if ligne.startswith("E  ") and "assert" not in ligne[:12]:
                msg = ligne.strip()[:150]
                break
        if not msg:
            m = re.search(r"^E\s+(.*)$", r.stdout or "", re.M)
            msg = (m.group(1)[:150] if m else "(pas de message capture)")
        print("%-4s %-78s -> %s" % ("OK" if rouge else "FAIL", libelle,
                                    "ROUGE" if rouge else "VERT (garde INERTE)"))
        print("        %s" % msg)
        ok = ok and rouge
    print()
    print("VERDICT MUTATION : %s" % ("tous les mutants sont vus" if ok
                                     else "AU MOINS UNE GARDE EST INERTE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
