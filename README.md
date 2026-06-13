# MPI TSP Genetic Algorithm for LXD Cluster

Testowalny prototyp równoległego algorytmu genetycznego dla problemu komiwojażera TSP, zrealizowany w modelu wyspowym z użyciem MPI i kontenerów systemowych LXD.

Podstawowy model wykonania:

```text
1 kontener LXD = 1 wyspa algorytmu genetycznego = 1 proces MPI = 1 rank MPI
```

LXD dostarcza izolowane środowiska wykonawcze, natomiast podział pracy, komunikacja, migracja osobników i zbieranie wyników są realizowane przez MPI.

## Infrastruktura

Docelowy wariant eksperymentu zakłada klaster z 3 węzłami LXD. Na każdym węźle uruchamiane są kontenery systemowe pełniące rolę wysp algorytmu genetycznego.

```text
3 węzły LXD
4 kontenery LXD na węzeł
12 kontenerów / ranków MPI łącznie
1 vCPU na kontener
4 GiB RAM na kontener
```

Do eksperymentów skalowania używane są jawne pliki hostów MPI:

```text
hosts-1-per-node.lxd  -> 3 ranki,  po 1 kontenerze na węzeł
hosts-2-per-node.lxd  -> 6 ranków, po 2 kontenery na węzeł
hosts-4-per-node.lxd  -> 12 ranków, po 4 kontenery na węzeł
hosts-8-per-node.lxd  -> 24 ranki, po 8 kontenerów na węzeł (wariant rozszerzony)
```

Wariant MPI korzysta również z infrastruktury przygotowanej ponad podstawową konfiguracją LXD:

- prywatny DNS oparty o `dnsmasq`, z nazwami kontenerów w domenie `.lxd`,
- prywatna sieć VPN oparta na WireGuard między węzłami,
- sieć typu overlay dla komunikacji kontenerów ponad rozproszonymi hostami,
- pliki `hosts-*.lxd` przekazywane do `mpirun --hostfile`,
- OpenMPI i `mpi4py` wewnątrz kontenerów,
- profil LXD `mpi-worker` z limitami `limits.cpu=1` i `limits.memory=4GiB`,
- skrypty pomocnicze do zapisu DNS, uruchamiania eksperymentów i pobierania wyników.

## Parametry finalnych eksperymentów MPI

W raporcie końcowym opisane są dwie główne grupy eksperymentów: skalowanie liczby procesów MPI oraz porównanie strategii migracji.

Wspólne parametry algorytmu:

| Parametr | Wartość |
|---|---|
| Dane wejściowe | `inputs/mazowieckie_114.csv` |
| Liczba miast | `114` |
| Tryb populacji | `--population-mode total` |
| Populacja całkowita | `1800` |
| Liczba generacji | `100` |
| Mutacja | `0.15`, mutacja typu swap |
| Elityzm | `2` |
| Selekcja | turniejowa, `--tournament 4` |
| Krzyżowanie | ordered crossover |
| Lokalna poprawa | `--two-opt-attempts 5` |
| Limity kontenera | `1 vCPU`, `4GiB RAM` |

Eksperyment skalowania MPI:

| Parametr | Wartość |
|---|---|
| Grupa wyników | `skalowanie-005` |
| Skrypt | `mpi_experiment_scaling.sh` |
| Pliki hostów | `hosts-1-per-node.lxd`, `hosts-2-per-node.lxd`, `hosts-4-per-node.lxd` |
| Liczba ranków | `3`, `6`, `12` |
| Populacja na rank | `600`, `300`, `150` |
| Strategia migracji | `none` |
| Interwał migracji | `25`, zapisany w konfiguracji, ale bez realnej wymiany dla `none` |
| Liczba imigrantów | `0` |

Eksperyment migracji MPI:

| Parametr | Wartość |
|---|---|
| Grupa wyników | `migracja-002` |
| Skrypt | `mpi_experiment_migration.sh` |
| Plik hostów | `hosts-4-per-node.lxd` |
| Liczba ranków | `12` |
| Populacja na rank | `150` |
| Strategie | `none`, `ring`, `global-best` |
| `none` | `migration-interval=50`, `immigrants=0` |
| `ring` | `migration-interval=50`, `immigrants=2` |
| `global-best` | `migration-interval=100`, `immigrants=1` |

Wykresy w raporcie są generowane z zagregowanych wyników tworzonych przez `evaluate_scaling.py` i `evaluate_migration.py`. Dane na wykresach są uśredniane z 10 niezależnych uruchomień dla każdego eksperymentu, aby ograniczyć wpływ losowości algorytmu genetycznego.

## Interpretacja populacji

Program rozróżnia dwa tryby interpretacji parametru `--population`:

```text
--population-mode per-rank   --population oznacza populację na każdej wyspie/ranku MPI
--population-mode total      --population oznacza łączny budżet populacji dzielony przez liczbę ranków MPI
```

W finalnych eksperymentach MPI używany jest tryb `total`, np.:

```text
population=1800, ranks=12
rank 0..11: 150 osobników
łącznie: 1800 osobników
```

Tryb `total` jest używany w eksperymencie skalowania, ponieważ utrzymuje stały całkowity budżet populacji przy różnej liczbie ranków. Dzięki temu porównanie czasu wykonania nie jest zaburzone tym, że większa liczba procesów wykonywałaby większą całkowitą pracę.

## Struktura projektu

```text
mpi-tsp-ga/
├── tsp_ga/
│   ├── __init__.py
│   ├── models.py
│   ├── config.py
│   ├── problem.py
│   ├── operators.py
│   ├── evolution.py
│   ├── migration.py
│   ├── mpi_runtime.py
│   ├── timing.py
│   ├── reporting.py
│   ├── runner.py
│   └── cli.py
├── main.py
├── mpi_run_ga.sh
├── mpi_experiment_scaling.sh
├── mpi_experiment_migration.sh
├── evaluate_scaling.py
├── evaluate_migration.py
├── plot_scaling.py
├── plot_migration.py
├── pyproject.toml
└── README.md
```

## Moduły

| Plik | Odpowiedzialność |
|---|---|
| `models.py` | Modele danych, typy, konfiguracje i metryki runtime; bez importu `mpi4py` |
| `config.py` | Budowanie, walidacja i rozwiązywanie populacji per rank |
| `problem.py` | Wczytywanie/generowanie miast oraz macierz odległości |
| `operators.py` | Operatory GA: selekcja turniejowa, ordered crossover, mutacja swap, losowy 2-opt i walidacja tras |
| `evolution.py` | Ewolucja jednej generacji i elityzm |
| `migration.py` | Strategie migracji `none`, `ring` i `global-best` |
| `mpi_runtime.py` | Kontekst MPI i zbieranie wyników |
| `timing.py` | `StageTimer` do mierzenia etapów wykonania |
| `reporting.py` | Budowanie dokumentu wynikowego JSON, zapis JSON i krótki komunikat stdout |
| `runner.py` | Główny przebieg wariantu MPI |
| `cli.py` | Interfejs linii poleceń |
| `main.py` | Cienki entrypoint aplikacji |

## Przepływ wykonania

```text
main.py
  -> tsp_ga.cli.main()
      -> parse_args()
      -> build_config(args)
      -> validate_config(config)
      -> run_ga(config)
```

W trybie MPI:

```text
run_ga(config)
  -> get_mpi_context()
  -> build_population_plan(config.ga, mpi.size)
  -> resolve_ga_config_for_rank(config.ga, population_plan, mpi.rank)
  -> prepare_problem(experiment_config, mpi_context)
      rank 0:
        -> wczytuje miasta z --input albo generuje losowe punkty 2D
      all ranks:
        -> comm.bcast(cities, root=0)
        -> build_distance_matrix(cities)
  -> run_island(effective_ga_config, rng_seed, problem, mpi_context)
      -> initial_population(...)
      -> for each generation:
          -> evolve_one_generation(...)
          -> optional migration
      -> IslandResult z metrykami czasu migracji i ewolucji
  -> collect_results(...)
      -> comm.gather(local_result, root=0)
  -> rank 0 only:
      -> finalize_run(...)
```

Wszystkie ranki rozwiązują tę samą instancję TSP. Rank 0 przygotowuje listę miast i rozsyła ją przez `comm.bcast(cities, root=0)`. Każdy rank buduje tę samą macierz odległości, ale używa innego ziarna RNG, więc startuje z inną populacją początkową.

## Strategie migracji

Program obsługuje trzy strategie migracji:

```text
none         brak migracji; wyspy pracują niezależnie
ring         migracja pierścieniowa: rank i -> rank i+1
global-best  każda wyspa wysyła elity, a wszystkie wyspy dostają globalną pulę elit
```

Strategia `ring` używa MPI `sendrecv()` i wymienia najlepsze osobniki tylko z sąsiednim rankiem. Strategia `global-best` używa `allgather()` i udostępnia pulę elit wszystkim rankom. W wynikach raportu `ring` dał najlepszy kompromis jakości, różnorodności i kosztu komunikacji, natomiast `global-best` szybko ujednolicił populacje.

## Wynik programu

Program zawsze zapisuje pełny wynik do pliku JSON wskazanego przez wymagany parametr `--output`.

Na stdout wypisywana jest tylko jedna krótka linia podsumowania:

```text
DONE run_id=... mode=mpi ranks=12 cities=114 population_total=1800 best_distance=... edge_diversity_mean=... elapsed_seconds=... migration_seconds=... output=results/...
```

Aktualna struktura pliku JSON:

```text
run
params
metrics
  quality_measures
  performance_measures
islands
notes
```

Najważniejsze pola `params`:

```text
input
cities
seed
islands
generations
population_mode
population_total
population_per_island
mutation
elite
tournament
two_opt_attempts
migration_strategy
migration_interval
immigrants
cpu_limit
memory_limit
```

Najważniejsze metryki jakości:

```text
best_distance
mean_island_distance
distance_spread
improvement_vs_none_percent
diversity.mean_pairwise_edge_distance
best_route.route_fingerprint
```

Najważniejsze metryki wydajności:

```text
total_time_seconds_T_p
relative_speedup_S_ref
relative_efficiency_E_ref
elapsed_seconds
prepare_problem_seconds
run_island_seconds
gather_seconds
report_seconds
evolution_max_rank_seconds
migration_total_seconds
migration_count_total
migration_overhead_ratio
```

## Metryka różnorodności tras

Różnorodność najlepszych tras między wyspami jest liczona przez podobieństwo krawędzi cyklu TSP.

```text
edge_distance = 1 - liczba_wspólnych_krawędzi / liczba_krawędzi
```

Interpretacja:

```text
0.0  najlepsze trasy mają identyczny zbiór krawędzi
1.0  najlepsze trasy nie mają wspólnych krawędzi
```

Ta metryka jest szczególnie przydatna przy porównaniu `none`, `ring` i `global-best`, ponieważ pokazuje, czy migracja nie doprowadziła do przedwczesnego ujednolicenia wysp.

## Uruchomienie eksperymentów raportowych

Eksperyment skalowania zgodny z raportem:

```bash
./mpi_experiment_scaling.sh \
  --hostfiles ./hosts-1-per-node.lxd,./hosts-2-per-node.lxd,./hosts-4-per-node.lxd \
  --run-group-id skalowanie-005 \
  --input inputs/mazowieckie_114.csv \
  --seeds 32345 \
  --population 1800 \
  --generations 100 \
  --python .venv/bin/python \
  --fetch
```

Eksperyment migracji zgodny z raportem:

```bash
./mpi_experiment_migration.sh \
  --hostfile ./hosts-4-per-node.lxd \
  --migration-strategy all \
  --run-group-id migracja-002 \
  --input inputs/mazowieckie_114.csv \
  --seeds 32345 \
  --population 1800 \
  --generations 100 \
  --python .venv/bin/python \
  --fetch
```

Dla pełnej serii uśrednianej na wykresach należy przekazać do `--seeds` listę 10 niezależnych ziaren w formacie CSV.

Agregacja wyników:

```bash
.venv/bin/python evaluate_scaling.py \
  --summary results/runs.tsv \
  --run-group-id skalowanie-005

.venv/bin/python evaluate_migration.py \
  --summary results/runs.tsv \
  --run-group-id migracja-002
```

Generowanie wykresów:

```bash
.venv/bin/python plot_scaling.py \
  results/evaluate-scaling-skalowanie-005.json \
  --sequential results/sequential-12345.json

.venv/bin/python plot_migration.py \
  results/evaluate-quality-migracja-002.json
```

## Instalacja

Rekomendowany sposób instalacji w środowisku developerskim:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Dla środowiska developerskiego z narzędziami pomocniczymi:

```bash
pip install -e ".[dev]"
```

Uruchomienie pomocy CLI:

```bash
.venv/bin/python main.py --help
```

## Instalacja w kontenerach LXD

Na każdym kontenerze LXD wymagane są Python, OpenMPI, `mpi4py` i serwer SSH:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv openmpi-bin libopenmpi-dev openssh-server
```

Następnie w katalogu projektu:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Jeżeli projekt jest tylko szybko testowany w kontenerze bez venv, można użyć wariantu awaryjnego:

```bash
python3 -m pip install --break-system-packages mpi4py
```

## Limity zasobów LXD

Limity `1 vCPU` i `4GiB RAM` należy ustawić w konfiguracji LXD, najlepiej na profilu `mpi-worker`, którego używają kontenery MPI. Plik `lxd_profile_mpi_worker.yaml` zawiera dane cloud-init dla kontenerów i sam z siebie nie nakłada limitów CPU/RAM.

Rekomendowany sposób:

```bash
./lxd_apply_mpi_worker_limits.sh
```

Równoważne komendy LXD:

```bash
lxc profile set mpi-worker limits.cpu 1
lxc profile set mpi-worker limits.memory 4GiB
```

Weryfikacja:

```bash
lxc profile show mpi-worker
lxc config show <container-name> --expanded
```

## Test lokalny z MPI

```bash
mpiexec -n 4 .venv/bin/python main.py \
  --cities 50 \
  --population-mode total \
  --population 400 \
  --generations 300 \
  --migration-strategy ring \
  --migration-interval 25 \
  --immigrants 2 \
  --output results/mpi-local-004.json
```

## Uwagi projektowe

- Program zawsze zapisuje pełny wynik do JSON przez wymagany parametr `--output`.
- `models.py` nie importuje `mpi4py`, dzięki czemu modele i większość logiki GA można testować bez inicjalizacji MPI.
- Operator `random_two_opt_improvement()` wykonuje losowe próby ulepszenia trasy i używa delta-cost O(1).
- Dla wyboru elit i migrantów używane jest `heapq.nsmallest`, co ogranicza koszt względem pełnego sortowania.
- `--debug-routes` warto włączać w testach i podczas rozwoju, ale wyłączać w dłuższych benchmarkach.
- Wariant MPI nie używa natywnego schedulera LXD do podziału pracy. LXD zapewnia kontenery, a MPI zapewnia dystrybucję obliczeń i komunikację między rankami.
