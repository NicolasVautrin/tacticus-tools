ASCII STRICT ici : ce fichier est relu par un script PowerShell 5.1 (encodage ANSI).
Un tiret long ou un guillemet francais y sort en mojibake dans le contexte reinjecte.

**AGENTS EN VOL -- ne PAS (re)injecter Frida ni redemarrer le host tant qu'ils tournent.**
- #100 residus AnvilShield (ApplyStun + FrozenAttackerAdvantage)
- #95  contributions Waaagh (effets 1100/1101)
- #90  reste : 5 abilities MoW des groupes B/C/D
A leur retour : relire la PR, RE-VALIDER soi-meme (tests cibles, jamais la suite), merger,
puis relancer un solveur pour garder la file a ~3.

**GESTE DIFFERE** : reinject des hooks du (stopAfterCapture est passe en DEFAUT, la session
tourne encore avec les anciens). Des que plus aucun agent ne tourne :
build:hooks deja fait -> POST /api/admin/inject -> warmup.

**DECISION OUVERTE** : perimetre de la migration VA -> symbole. Fait : scripts/python/**,
.claude/skills, CLAUDE.md. RESTE docs/rl/ (~3400 occurrences), non tranche.
Outil pret et idempotent : migrate_va_to_symbol.py <chemin> --ext .md --apply

**CE QUI VIENT D'ETRE FAIT** (ne pas re-deriver) :
- migration VA -> symbole + table de symboles VERSIONNEE sous data/symbols/<HASH>/{frida,ghidra}/
- procedure de MAJ du jeu ecrite dans le skill tacticus-orchestration (PAS dans le CLAUDE.md)
- CLAUDE.md repense POUR UN AGENT : 173,6 Ko -> 83,4 Ko de contexte permanent
- #101 merge (fork de port "a bouge ce tour" -> store unique UnitFlag.Moved)
- #77 enrichie : le registre des runners a un ramasse-miettes branche sur un declencheur MORT
  (le front /view/, plus utilise) -> /api/runners MENT (85 entrees pour 1 vivant). La verite
  est le RPC listRunners. Runner 28 laisse en place : sans champ owner, indecidable.
