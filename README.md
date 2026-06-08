
```markdown
# MPI TSP Genetic Algorithm for LXD Cluster

Testowalny prototyp równoległego algorytmu genetycznego dla problemu komiwojażera TSP, zrealizowany w modelu wyspowym z użyciem MPI.

Projekt jest przygotowany pod uruchamianie w klastrze LXD, gdzie:

```text
1 kontener LXD = 1 wyspa algorytmu genetycznego = 1 proces MPI = 1 rank MPI
```

LXD dostarcza izolowane środowiska wykonawcze, natomiast podział pracy, komunikacja i migracja osobników są realizowane przez MPI.

## Kluczowe założenie eksperymentalne

Program rozróżnia dwa tryby interpretacji populacji:

```text
--population-mode per-rank   --population oznacza populację na każdej wyspie/ranku MPI
--population-mode total      --population oznacza łączny budżet populacji dzielony przez liczbę ranków MPI
```

W trybie `total` populacja jest dzielona z obsługą reszty, np.:

```text
population=1000, ranks=6
rank 0..3: 167 osobników
rank 4..5: 166 osobników
łącznie: 1000 osobników
```

Do badania jakości modelu wyspowego można używać `per-rank`, bo wraz z liczbą wysp rośnie całkowity budżet obliczeń.

Do badania przyspieszenia `S(n,p) = T(n,1) / T(n,p)` bardziej uczciwy jest tryb `total`, ponieważ całkowity budżet populacji pozostaje zbliżony między `p=1` i `p>1`.

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
├── pyproject.toml
└── README.md
```

## Moduły

| Plik | Odpowiedzialność |
|---|---|
| `models.py` | Modele danych, typy, konfiguracje i metryki runtime; bez importu `mpi4py` |
| `config.py` | Budowanie, walidacja i rozwiązywanie populacji per rank |
| `problem.py` | Wczytywanie/generowanie miast oraz macierz odległości |
| `operators.py` | Operatory GA: selekcja, crossover, mutacja, losowy 2-opt delta O(1), walidacja trasy O(n) |
| `evolution.py` | Ewolucja jednej generacji; elita przez `heapq.nsmallest` |
| `migration.py` | Strategie migracji `none`, `ring` i `global-best`; migranci przez `heapq.nsmallest` |
| `mpi_runtime.py` | Kontekst MPI i zbieranie wyników |
| `timing.py` | Prosty `StageTimer` do mierzenia etapów wykonania |
| `reporting.py` | Budowanie dokumentu wynikowego JSON, zapis JSON i krótki komunikat stdout |
| `runner.py` | Uruchamianie wariantu MPI |
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

Aplikacja uruchamia wariant MPI: wiele wysp, jedna wyspa na rank MPI.

W trybie MPI:

```text
run_ga(config)
  -> get_mpi_context()
  -> build_population_plan(config.ga, mpi.size)
  -> resolve_ga_config_for_rank(config.ga, population_plan, mpi.rank)
  -> prepare_problem(experiment_config, mpi_context)
      rank 0:
        -> load cities albo generate synthetic cities
      all ranks:
        -> comm.bcast(cities, root=0)
        -> build_distance_matrix(cities)
  -> run_island(effective_ga_config, rng_seed, problem, mpi_context)
      -> initial_population(...)
      -> for each generation:
          -> evolve_one_generation(...)
          -> migration according to --migration-strategy
      -> IslandResult z metrykami czasu migracji i ewolucji
  -> collect_results(...)
      -> comm.gather(local_result, root=0)
  -> rank 0 only:
      -> finalize_run(...)
```

## Strategie migracji

Program obsługuje trzy strategie migracji:

```text
none         brak migracji; wyspy pracują niezależnie
ring         migracja pierścieniowa: rank i -> rank i+1
global-best  każda wyspa wysyła swoje elity, a wszystkie wyspy dostają globalną pulę elit
```

### `global-best`

Strategia `global-best` działa przez MPI `allgather()`:

```text
1. każda wyspa wybiera swoich najlepszych --immigrants osobników,
2. wszystkie wyspy wymieniają te listy przez allgather,
3. każda wyspa otrzymuje globalną pulę elit ze wszystkich ranków,
4. każda wyspa scala lokalną populację z globalną pulą,
5. każda wyspa zachowuje najlepsze osobniki do swojego lokalnego rozmiaru populacji.
```

Dla `p` ranków i `m` migrantów na rank każda wyspa dostaje do rozważenia do `p × m` osobników globalnych. To zwiększa koszt komunikacji względem `ring`, ale szybciej propaguje dobre rozwiązania.

Zalecane parametry dla `global-best`:

```text
--immigrants 1 albo 2
--migration-interval 50 albo 100
```

Ta strategia jest dobra jako wariant eksperymentalny do porównania wpływu topologii migracji na jakość rozwiązania, szybkość zbieżności i narzut komunikacji.

## Optymalizacje złożoności obliczeniowej

### Walidacja trasy O(n)

`validate_route()` używa `collections.Counter`, więc wykrycie duplikatów, braków i nieoczekiwanych miast jest liniowe względem liczby miast.

### Losowy 2-opt z oceną delta O(1)

`random_two_opt_improvement()` nie przelicza całej długości trasy po każdej próbie. Liczy zmianę kosztu tylko dla czterech krawędzi:

```text
stare: (a,b), (c,d)
nowe:  (a,c), (b,d)
```

Ocena pojedynczej próby 2-opt ma koszt O(1), a losowanie segmentu pomija nieużyteczne pary sąsiadujące.

### `heapq.nsmallest` zamiast pełnego sortowania

Dla wyboru elity i migrantów używane jest:

```python
heapq.nsmallest(k, pop, key=lambda ind: ind.distance)
```

Dla małego `k` ogranicza to koszt z pełnego sortowania `O(n log n)` do około `O(n log k)`.

### `best_seen`

Wyspa trzyma najlepszy historycznie znaleziony osobnik jako `best_seen`. Nie zakładamy, że najlepszy osobnik zawsze pozostanie w aktualnej populacji po zmianie strategii migracji lub ewolucji.

## Wynik programu

Program zawsze zapisuje pełny wynik do pliku JSON wskazanego przez wymagany parametr `--output`.

Na stdout wypisywana jest tylko jedna krótka linia podsumowania, np.:

```text
DONE run_id=lxd-3nodes-2containers-001 mode=mpi ranks=6 cities=100 population_total=1200 best_distance=1234.567890 edge_diversity_mean=0.420000 elapsed_seconds=12.345678 migration_seconds=0.123456 output=results/lxd-3nodes-2containers-001.json
```

## Metryki dywersyfikacji

Wynik JSON zawiera sekcję `diversity`, która opisuje podobieństwo najlepszych tras znalezionych przez wyspy.

Trasa TSP jest zamieniana na zbiór nieskierowanych krawędzi cyklu. Odległość między dwiema trasami jest liczona jako:

```text
edge_distance = 1 - liczba_wspólnych_krawędzi / liczba_krawędzi
```

Interpretacja:

```text
0.0  najlepsze trasy mają identyczny zbiór krawędzi
1.0  najlepsze trasy nie mają wspólnych krawędzi
```

Sekcja `diversity` zawiera:

```text
unique_best_routes
pairwise_comparisons
mean_pairwise_edge_distance
min_pairwise_edge_distance
max_pairwise_edge_distance
```

Ta metryka jest szczególnie przydatna przy porównaniu `none`, `ring` i `global-best`, bo pokazuje, czy migracja nie doprowadziła do przedwczesnego ujednolicenia wysp.

## Metryki komunikacji i czasu

Wynik JSON zawiera:

```text
prepare_problem_seconds
run_island_seconds
gather_seconds
report_seconds
total_seconds
migration_time_total_all_ranks
migration_count_total_all_ranks
migration_time_avg_per_migration
migration_time_max_rank
evolution_time_max_rank
```

Oraz sekcję dywersyfikacji:

```text
unique_best_routes
mean_pairwise_edge_distance
min_pairwise_edge_distance
max_pairwise_edge_distance
```

Dzięki temu można porównać koszt lokalnych obliczeń z narzutem komunikacji MPI/LXD.

## Instalacja jako pakiet lokalny

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

Uruchomienie z katalogu projektu:

```bash
python3 main.py --help
```

Alternatywnie, bez instalacji jako pakiet, trzeba uruchamiać program z katalogu głównego projektu, tak aby Python widział katalog `tsp_ga/` na `PYTHONPATH`.

### Instalacja w kontenerach LXD

Na każdym kontenerze LXD wymagane są Python, OpenMPI i `mpi4py`:

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

Docelowo lepiej używać `venv` i `pip install -e .`, bo wtedy importy modułów `tsp_ga.*` są przewidywalne.

## Test lokalny z MPI

```bash
mpiexec -n 4 python3 main.py \
  --cities 50 \
  --population-mode total \
  --population 400 \
  --generations 300 \
  --migration-strategy ring \
  --migration-interval 25 \
  --immigrants 2 \
  --run-id mpi-local-004 \
  --scenario-name local-4-ranks \
  --output results/mpi-local-004.json
```

Przykład z migracją `global-best`:

```bash
mpiexec -n 4 python3 main.py \
  --cities 50 \
  --population-mode total \
  --population 400 \
  --generations 300 \
  --migration-strategy global-best \
  --migration-interval 50 \
  --immigrants 1 \
  --run-id mpi-local-004-global-best \
  --scenario-name local-4-ranks-global-best \
  --output results/mpi-local-004-global-best.json
```

## Uruchomienie na klastrze LXD

```bash
mpiexec --hostfile hosts.lxd -n 6 python3 main.py \
  --cities 100 \
  --population-mode total \
  --population 1200 \
  --generations 1000 \
  --migration-strategy ring \
  --migration-interval 50 \
  --immigrants 4 \
  --two-opt-attempts 5 \
  --metadata-containers-per-node 2 \
  --hostfile hosts.lxd \
  --cpu-limit 1 \
  --code-version manual-v1 \
  --run-id lxd-3nodes-2containers-001 \
  --scenario-name 3nodes-2containers-per-node \
  --output results/lxd-3nodes-2containers-001.json
```

Wariant `global-best` na klastrze LXD:

```bash
mpiexec --hostfile hosts.lxd -n 6 python3 main.py \
  --cities 100 \
  --population-mode total \
  --population 1200 \
  --generations 1000 \
  --migration-strategy global-best \
  --migration-interval 100 \
  --immigrants 1 \
  --two-opt-attempts 5 \
  --metadata-containers-per-node 2 \
  --hostfile hosts.lxd \
  --cpu-limit 1 \
  --code-version manual-v1 \
  --run-id lxd-3nodes-2containers-global-best-001 \
  --scenario-name 3nodes-2containers-global-best \
  --output results/lxd-3nodes-2containers-global-best-001.json
```

## Parametry CLI

| Parametr | Znaczenie |
|---|---|
| `--population-mode per-rank|total` | Interpretacja `--population` |
| `--population` | Populacja per rank albo całkowity budżet populacji |
| `--migration-strategy none|ring|global-best` | Strategia migracji między wyspami |
| `--cities` | Liczba syntetycznie generowanych miast |
| `--input` | Plik CSV z miastami |
| `--generations` | Liczba generacji |
| `--mutation` | Prawdopodobieństwo mutacji swap |
| `--elite` | Liczba najlepszych osobników przenoszonych do kolejnej generacji |
| `--tournament` | Rozmiar turnieju w selekcji turniejowej |
| `--migration-interval` | Co ile generacji wykonywać migrację |
| `--immigrants` | Ilu najlepszych osobników migruje do kolejnej wyspy |
| `--two-opt-attempts` | Liczba losowych prób lokalnego ulepszenia trasy |
| `--debug-routes` | Walidacja, czy trasy są poprawnymi permutacjami |
| `--hostfile` | Hostfile MPI zapisany jako metadane wyniku |
| `--cpu-limit` | Limit CPU kontenera zapisany jako metadane wyniku |
| `--code-version` | Wersja kodu/commit/tag zapisany jako metadane wyniku |
| `--output` | Wymagana ścieżka zapisu wyniku JSON |
| `--run-id` | Identyfikator uruchomienia eksperymentu |
| `--scenario-name` | Nazwa scenariusza eksperymentalnego |
| `--metadata-containers-per-node` | Metadane wyniku: liczba kontenerów LXD na fizyczny node |

## Miary do eksperymentów

Dla pomiaru przyspieszenia używaj `--population-mode total` i porównuj uruchomienia MPI z różną liczbą ranków:

```bash
mpiexec --hostfile hosts.lxd -n 1 python3 main.py --migration-strategy none --population-mode total --population 1200 --cities 100 --generations 1000 --output results/t1.json
mpiexec --hostfile hosts.lxd -n 6 python3 main.py --population-mode total --population 1200 --cities 100 --generations 1000 --output results/t6.json
```

Następnie:

```text
S(n,6) = elapsed_seconds z t1.json / elapsed_seconds z t6.json
```

## Uwagi projektowe

- Program zawsze zapisuje pełny wynik do JSON przez wymagany parametr `--output`; stdout zawiera tylko krótkie podsumowanie.
- Pomiar etapów wykonania jest wydzielony do `tsp_ga/timing.py` jako `StageTimer`, żeby `runner.py` nie powielał ręcznej logiki start/stop.
- W raporcie JSON pole `ga_config_effective_rank0` oznacza efektywną konfigurację ranku 0. Pełny rozkład populacji między rankami jest zapisany w `work_budget.per_rank_populations`.
- `models.py` nie importuje `mpi4py`, dzięki czemu modele i większość logiki GA można testować bez inicjalizacji MPI.
- Migracja ma jawnie wybieraną strategię: `none`, `ring` albo `global-best`.
- Wynik JSON zawiera metrykę dywersyfikacji najlepszych tras między wyspami, opartą o podobieństwo krawędzi TSP.
- Operator `random_two_opt_improvement()` wykonuje losowe próby ulepszenia trasy i używa delta-cost O(1).
- `--debug-routes` warto włączać w testach i podczas rozwoju, ale wyłączać w dłuższych benchmarkach.
- Wariant MPI nie używa natywnego schedulera LXD. LXD zapewnia kontenery, a MPI zapewnia dystrybucję pracy.
```
