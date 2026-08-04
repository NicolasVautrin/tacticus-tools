# #437-r1 -- l'ecart de 1 sur le degat du tir d'overwatch

## 1. Le rouge, re-confirme sur `origin/master`

`python probe_437_overwatch_consumes_armour.py --verdict` (board `MC1_67`, seed `4321`,
overwatcher `eldarRanger` seul) :

```
[437] NATIF : armure avant=True  apres=False | hp 400000 -> 398816 (delta=1184) | tirs=1
[437] PORT  (mutate=False) : armure apres=False | hp 400000 -> 398817 (delta=1183)
[437] VERDICT : 1 echec(s)
   - [port] degat du tir d'overwatch : port=1183 natif=1184 (ecart -1)
```

Meme ecart dans le regime a DEUX tirs (`--overwatchers eldarRanger,admecDestroyer`) : hp_after
natif `384720` / port `384721` sur 400000 PV, soit degat natif `15280` / port `15279`.

Le flag d'armure (`EffectComponent.IsActive @+0x5c`) tombe des DEUX cotes : le foyer `On(9)`
livre par #437 tient. Le residu est purement ARITHMETIQUE, sur le degat du tir.

(En cours -- l'etage divergent est etabli plus bas.)
