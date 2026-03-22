# Priority Dashboard & Simulation

A TUI-based priority dashboard and large-scale simulation for understanding Slurm's multifactor priority system — fairshare, job aging, QOS, and how they interact to determine queue ordering.

## Quick Start

```bash
# 1. Start the cluster (if not already running)
make playground-start

# 2. Set up the simulation (~50 users, ~15 accounts, ~30k jobs)
playground simulate setup

# 3. Watch the priority dashboard
playground priority live

# 4. Clean up when done
playground simulate teardown
```

## Commands Reference

### `playground priority`

View job priority, fairshare, and queue ranking.

| Command | Description |
|---------|-------------|
| `playground priority live` | Real-time TUI with all 4 dashboard sections, auto-refreshing |
| `playground priority watch` | Compact one-liner that refreshes — perfect for a tmux pane |
| `playground priority show` | One-shot snapshot of the full dashboard |
| `playground priority fairshare` | Fairshare table for all accounts/users |
| `playground priority factors` | Priority factor breakdown for pending jobs |
| `playground priority explain <JOB_ID>` | Deep-dive into one job's priority calculation |
| `playground priority tmux-status` | Short string for tmux status bar integration |

**Options for `live` and `show`:**

```bash
-u, --user <name>      Highlight a specific user's rows (reverse video)
-a, --account <name>   Highlight a specific account's rows
-r, --refresh <secs>   Refresh interval for live mode (default: 3)
```

**Options for `factors`:**

```bash
-u, --user <name>      Filter to only show a specific user's jobs
```

### `playground simulate`

Set up and tear down large-scale priority simulations.

| Command | Description |
|---------|-------------|
| `playground simulate setup` | Build the full simulation environment |
| `playground simulate teardown` | Remove everything and restore defaults |
| `playground simulate status` | Check if a simulation is currently active |

**Options for `setup`:**

```bash
--jobs-scale <float>     Scale factor for job count (default: 1.0 ≈ 30k jobs)
                         Use 0.5 for ~15k jobs, 2.0 for ~60k jobs
--cpus-per-node <int>    Virtual CPUs per node (default: 1000)
                         Controls the running vs pending job ratio
--seed <int>             Random seed for reproducible job distributions
```

**Examples:**

```bash
# Default: ~30k jobs, ~5k running
playground simulate setup

# Smaller simulation for quick testing
playground simulate setup --jobs-scale 0.1 --seed 42

# Larger simulation with more pending jobs
playground simulate setup --jobs-scale 2.0 --cpus-per-node 500
```

## Dashboard Sections

The `playground priority live` TUI shows four sections:

### 1. Fairshare by Account/User

Shows each account and user's fairshare score with color-coded bars:
- **Green (0.8-1.0):** Under-utilizing allocation — jobs get boosted
- **Yellow (0.3-0.5):** Moderate usage
- **Red (0.0-0.1):** Over-utilizing — jobs get deprioritized

Columns: Account, User, RawShares, FairShare (score + bar), RawUsage, EffUsage, LevelFS

### 2. Job Queue (sorted by priority)

All jobs in the queue ordered by priority score. Pending jobs get a queue position rank (#1, #2, ...) showing where they sit relative to other pending jobs.

Columns: Rank, JobID, Name, User, Account, State, Priority, Reason

### 3. Priority Factor Breakdown

For each pending job, shows the individual scores from each priority factor and identifies the **dominant factor** — the single biggest contributor to that job's priority.

Columns: JobID, User, Priority (total + bar), Age, FairShare, JobSize, Partition, QOS, Biggest Factor

### 4. Active Priority Weights

The currently configured weights from slurm.conf, so you can see how each factor is scaled:
- Age: 1000
- Fairshare: 10000 (dominant by design)
- JobSize: 500
- Partition: 1000
- QOS: 2000

## How the Simulation Works

### Architecture

The simulation creates a realistic HPC environment without requiring 100 physical machines:

```
┌─────────────────────────────────────────┐
│ Docker Host                             │
│                                         │
│  ┌─────────┐  ┌────┐ ┌────┐ ┌────┐    │
│  │slurmctld│  │ c1 │ │ c2 │ │ c3 │... │
│  │         │  │1000│ │1000│ │1000│    │
│  │         │  │CPUs│ │CPUs│ │CPUs│    │
│  └─────────┘  └────┘ └────┘ └────┘    │
│                                         │
│  Each node reports 1000 virtual CPUs    │
│  via SlurmdParameters=config_overrides  │
│  Total: N nodes × 1000 = N,000 slots   │
└─────────────────────────────────────────┘
```

`SlurmdParameters=config_overrides` tells Slurm to trust the configured CPU/memory values rather than detecting actual hardware. This lets a 2-CPU container accept 1000 simultaneous single-CPU jobs.

### Account Hierarchy

15 accounts with varying share weights simulate different research groups:

```
root
├── physics (200 shares) ── user01-04 [heavy]
├── cs (180 shares)      ── user13-17 [heavy]
├── genomics (160 shares)── user29-32 [heavy]
├── chemistry (150)      ── user05-08 [medium]
├── biology (150)        ── user09-12 [medium]
├── climate (130)        ── user45-47 [medium]
├── engineering (120)    ── user18-21 [medium]
├── neuroscience (110)   ── user36-39 [medium]
├── materials (100)      ── user25-28 [medium]
├── energy (100)         ── user48-49 [light]
├── astronomy (90)       ── user33-35 [light]
├── math (80)            ── user22-24 [light]
├── economics (60)       ── user40-42 [light]
├── admin (50)           ── user50    [light]
└── linguistics (40)     ── user43-44 [light]
```

Heavy accounts submit more jobs, depleting their fairshare faster. Light accounts remain under-utilized and get priority boosts — exactly how fairshare works in production.

### Job Distribution

Jobs are submitted as arrays for efficiency (~50 sbatch calls instead of ~30,000):

| Profile | Jobs per user | Total jobs (approx) |
|---------|--------------|---------------------|
| Heavy   | 800-1,200    | ~14,000 |
| Medium  | 300-600      | ~9,000 |
| Light   | 100-250      | ~2,500 |

QOS distribution: 75% normal, 15% high, 5% urgent, 5% low

### Fairshare Asymmetry

After setup, the dashboard will show:
- **Heavy users** (physics, cs, genomics) with low fairshare (red) — they've consumed more than their share
- **Light users** (linguistics, admin, math) with high fairshare (green) — under-utilized
- **Pending jobs** from light users ranked higher than heavy users despite submitting later

This demonstrates Slurm's core fairshare principle: the scheduler automatically compensates for past over-usage.

## Slurm Priority Primer

### Multifactor Priority

Slurm's `priority/multifactor` plugin calculates job priority as a weighted sum:

```
Priority = (Weight_Age × Age_Factor)
         + (Weight_FairShare × FairShare_Factor)
         + (Weight_JobSize × JobSize_Factor)
         + (Weight_Partition × Partition_Factor)
         + (Weight_QOS × QOS_Factor)
```

### Factors Explained

**Age** — How long the job has been waiting. Increases linearly from 0 to 1 over `PriorityMaxAge` (default 7 days). Prevents starvation.

**FairShare** — Compares a user's allocated share vs actual usage. Users who've consumed less than their share get a score near 1.0; over-consumers get near 0.0. This is the primary mechanism for equitable resource distribution.

**JobSize** — Based on the number of CPUs/nodes requested. Can favor small or large jobs depending on `PriorityFavorSmall`.

**Partition** — A fixed priority tier per partition. Useful for giving certain partitions (e.g., "interactive") higher base priority.

**QOS** — Quality of Service priority. Different QOS levels (low/normal/high/urgent) add fixed priority offsets.

### Key Configuration Parameters

| Parameter | Value | Effect |
|-----------|-------|--------|
| `PriorityWeightFairshare` | 10000 | Fairshare is the dominant factor |
| `PriorityWeightQOS` | 2000 | QOS is second most important |
| `PriorityWeightAge` | 1000 | Waiting time matters moderately |
| `PriorityWeightPartition` | 1000 | Partition priority matters moderately |
| `PriorityWeightJobSize` | 500 | Job size has minimal impact |
| `PriorityDecayHalfLife` | 7 days | Usage impact decays over a week |
| `PriorityMaxAge` | 7 days | Age factor maxes out after a week |
| `PriorityUsageResetPeriod` | Monthly | Usage counters reset each month |

### Reading the Dashboard

When looking at the priority dashboard, key things to notice:

1. **Fairshare gradient**: Accounts that submitted many jobs should show red/low fairshare. Accounts with few jobs should show green/high.

2. **Queue ordering vs submit order**: Pending jobs from high-fairshare users should be ranked above pending jobs from low-fairshare users, even if they were submitted later.

3. **Dominant factor column**: Shows what's driving each job's rank. Most jobs should show "FairShare" as dominant (since it has weight 10000). Jobs with `urgent` QOS may show "QOS" as dominant.

4. **The `explain` command**: Use `playground priority explain <JOB_ID>` on specific jobs to see the full calculation, contribution percentages, and where the job sits in the queue.

## Customizing the Simulation

### Changing Account Structure

Edit `ACCOUNTS` in `playground/cli/slurm_playground/simulate.py`:

```python
ACCOUNTS = [
    {"name": "mygroup", "shares": 200, "users": ["user01", "user02"], "profile": "heavy"},
    # ...
]
```

### Changing Job Distribution

Edit `PROFILE_JOBS` to adjust how many jobs each profile submits:

```python
PROFILE_JOBS = {
    "heavy":  (800, 1200),   # (min, max) jobs per user
    "medium": (300, 600),
    "light":  (100, 250),
}
```

### Changing QOS Tiers

Edit `QOS_TIERS` and `QOS_WEIGHTS`:

```python
QOS_TIERS = [
    {"name": "low",    "priority": 0,    "max_submit": 5000},
    {"name": "normal", "priority": 100,  "max_submit": 10000},
    # ...
]

# Distribution of jobs across QOS levels
QOS_WEIGHTS = {"low": 5, "normal": 75, "high": 15, "urgent": 5}
```

### Changing Priority Weights

Edit the `generate_simulation_slurm_conf()` function in `simulate.py`, or modify `config/25.05/slurm.conf` directly and run `scontrol reconfigure`.

### Running at Different Scales

```bash
# Small test (~3k jobs)
playground simulate setup --jobs-scale 0.1

# Default (~30k jobs)
playground simulate setup

# Large scale (~60k jobs)
playground simulate setup --jobs-scale 2.0

# More pending, fewer running (fewer CPU slots)
playground simulate setup --cpus-per-node 500

# Reproducible runs
playground simulate setup --seed 42
```

## Output Modes

Multiple ways to view priority data, depending on your workflow:

| Mode | Command | Best For |
|------|---------|----------|
| **Full TUI** | `playground priority live` | Dedicated monitoring terminal |
| **Watch line** | `playground priority watch -u you` | Small tmux pane split |
| **tmux status** | via `slurm-status.sh` | Always visible, zero effort |
| **Vim statusline** | via `slurm.vim` | See status without leaving editor |
| **One-shot** | `playground priority show` | Quick check |
| **JSON** | `playground priority watch --no-loop --format json` | Scripts/automation |

### Watch mode

A compact one-liner that refreshes in-place — run it in a narrow tmux split:

```bash
# Cluster overview
playground priority watch

# Personal status with queue rank
playground priority watch -u user01

# Account-level view
playground priority watch -a physics

# Slower refresh
playground priority watch -u user01 -r 10

# Print once for scripting
playground priority watch --no-loop --format json
```

### tmux + Vim integration

See [tmux/README.md](../tmux/README.md) for full setup instructions.

Quick start:
```bash
# In ~/.tmux.conf
set -g status-right '#(/path/to/playground/tmux/slurm-status.sh -u yourname)'
set -g status-interval 10

# In ~/.vimrc
source /path/to/playground/vim/slurm.vim
set statusline+=%{SlurmStatus()}
```

## Extending

### Adding New Priority Subcommands

Add new `@priority.command()` functions in `playground/cli/slurm_playground/priority.py`. The module provides helper functions:

- `run_in_slurmctld(cmd)` — execute commands in the slurmctld container
- `get_fairshare_data()` — parse `sshare` output into dicts
- `get_priority_factors()` — parse `sprio` output into dicts
- `get_queue_by_account()` — parse `squeue` with priority info
- `get_priority_config()` — get active priority weights from `scontrol`
- `_bar(value, max, width)` — render a mini bar chart
- `_fairshare_style(fs)` — get a color style for a fairshare value
- `_build_watch_line(user, account)` — build data dict for compact output
- `_format_watch_line(data)` — format data dict as one-liner string
- `_format_tmux_status(data, color, max_width)` — format for tmux status bar

### Adding Metrics to the Exporter

To expose priority data to Prometheus/Grafana, extend `monitoring/slurm-exporter/exporter.py` with gauges for fairshare scores, priority distributions, etc.

### Adding New Simulation Scenarios

Create new `@simulate.command()` functions in `simulate.py`, or create new experiment definitions in `playground/experiments/` following the existing YAML format.

## Upstream Compatibility

These features are implemented entirely in new files within the `playground/` directory:
- `playground/cli/slurm_playground/priority.py` — TUI dashboard + watch + tmux-status
- `playground/cli/slurm_playground/simulate.py` — simulation commands
- `playground/tmux/slurm-status.sh` — cached tmux status wrapper
- `playground/vim/slurm.vim` — Vim statusline integration
- `playground/docs/priority-simulation.md` — this documentation

The only existing file modified is `playground/cli/slurm_playground/main.py` (2 lines added: import + command registration). No upstream files (Dockerfile, docker-compose.yml, docker-entrypoint.sh, Makefile) are modified.

The simulation generates its own `slurm.conf` at runtime and restores the original on teardown, so static config changes don't accumulate.
