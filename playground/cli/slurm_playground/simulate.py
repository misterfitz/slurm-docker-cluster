"""Simulation commands for generating realistic priority/fairshare scenarios.

Creates ~50 users across ~15 accounts with ~30,000 jobs to exercise
the priority TUI dashboard at realistic HPC scale.
"""

import random
import subprocess
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

console = Console()

SCRIPT_DIR = Path(__file__).parent
CLI_DIR = SCRIPT_DIR.parent
PLAYGROUND_DIR = CLI_DIR.parent
PROJECT_DIR = PLAYGROUND_DIR.parent


# ── Account/User topology ──────────────────────────────────────────

ACCOUNTS = [
    {"name": "physics",      "shares": 200, "users": ["user01", "user02", "user03", "user04"],              "profile": "heavy"},
    {"name": "chemistry",    "shares": 150, "users": ["user05", "user06", "user07", "user08"],              "profile": "medium"},
    {"name": "biology",      "shares": 150, "users": ["user09", "user10", "user11", "user12"],              "profile": "medium"},
    {"name": "cs",           "shares": 180, "users": ["user13", "user14", "user15", "user16", "user17"],    "profile": "heavy"},
    {"name": "engineering",  "shares": 120, "users": ["user18", "user19", "user20", "user21"],              "profile": "medium"},
    {"name": "math",         "shares": 80,  "users": ["user22", "user23", "user24"],                        "profile": "light"},
    {"name": "materials",    "shares": 100, "users": ["user25", "user26", "user27", "user28"],              "profile": "medium"},
    {"name": "genomics",     "shares": 160, "users": ["user29", "user30", "user31", "user32"],              "profile": "heavy"},
    {"name": "astronomy",    "shares": 90,  "users": ["user33", "user34", "user35"],                        "profile": "light"},
    {"name": "neuroscience", "shares": 110, "users": ["user36", "user37", "user38", "user39"],              "profile": "medium"},
    {"name": "economics",    "shares": 60,  "users": ["user40", "user41", "user42"],                        "profile": "light"},
    {"name": "linguistics",  "shares": 40,  "users": ["user43", "user44"],                                  "profile": "light"},
    {"name": "climate",      "shares": 130, "users": ["user45", "user46", "user47"],                        "profile": "medium"},
    {"name": "energy",       "shares": 100, "users": ["user48", "user49"],                                  "profile": "light"},
    {"name": "admin",        "shares": 50,  "users": ["user50"],                                            "profile": "light"},
]

# Jobs per user by profile (creates fairshare asymmetry)
PROFILE_JOBS = {
    "heavy":  (800, 1200),   # heavy users submit 800-1200 jobs each
    "medium": (300, 600),    # medium users submit 300-600 each
    "light":  (100, 250),    # light users submit 100-250 each
}

QOS_TIERS = [
    {"name": "low",    "priority": 0,    "max_submit": 5000},
    {"name": "normal", "priority": 100,  "max_submit": 10000},
    {"name": "high",   "priority": 500,  "max_submit": 2000},
    {"name": "urgent", "priority": 1000, "max_submit": 500},
]

# QOS distribution weights (most jobs are normal)
QOS_WEIGHTS = {"low": 5, "normal": 75, "high": 15, "urgent": 5}


# ── Helpers ─────────────────────────────────────────────────────────

def get_docker_compose_cmd():
    """Get the docker compose command."""
    try:
        subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=True
        )
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose"]


def run_in_container(container: str, cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a command inside a specific container."""
    compose_cmd = get_docker_compose_cmd()
    full_cmd = compose_cmd + [
        "-f", str(PROJECT_DIR / "docker-compose.yml"),
        "exec", "-T", container, "bash", "-c", cmd,
    ]
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)


def run_in_slurmctld(cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a command inside the slurmctld container."""
    return run_in_container("slurmctld", cmd, check=check)


def is_cluster_running() -> bool:
    """Check if the Slurm cluster is running."""
    compose_cmd = get_docker_compose_cmd()
    result = subprocess.run(
        compose_cmd + [
            "-f", str(PROJECT_DIR / "docker-compose.yml"),
            "ps", "slurmctld", "--status", "running",
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def get_running_compute_nodes() -> list[str]:
    """Get list of running compute node container names."""
    compose_cmd = get_docker_compose_cmd()
    result = subprocess.run(
        compose_cmd + [
            "-f", str(PROJECT_DIR / "docker-compose.yml"),
            "ps", "--status", "running", "--format", "{{.Service}}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    services = result.stdout.strip().split("\n")
    # Compute nodes are services starting with c (c1, c2, ...) or similar
    return [s for s in services if s and s not in ("slurmctld", "slurmdbd", "mysql", "slurmrestd")]


def get_all_users() -> list[str]:
    """Get flat list of all simulation users."""
    users = []
    for acct in ACCOUNTS:
        users.extend(acct["users"])
    return users


def generate_simulation_slurm_conf(node_names: list[str], cpus_per_node: int = 1000) -> str:
    """Generate a slurm.conf tuned for simulation scale.

    This produces a self-contained config — it does NOT call scale.py functions,
    keeping scale.py untouched for upstream compatibility.
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    node_range = _compress_node_range(node_names)
    memory_per_node = 500000  # 500GB virtual

    return f"""# slurm.conf - Simulation configuration
# Generated by: playground simulate setup
# Timestamp: {timestamp}
#
# NOTE: This config over-provisions CPUs/memory for simulation purposes.
# Each node is configured with {cpus_per_node} CPUs to allow thousands of
# concurrent single-CPU jobs without requiring 100 real containers.

#
# Cluster Identity
#
ClusterName=linux
SlurmctldHost=slurmctld

#
# Authentication
#
AuthType=auth/munge

#
# Paths
#
SlurmctldPidFile=/var/run/slurm/slurmctld.pid
SlurmctldPort=6817
SlurmdPidFile=/var/run/slurm/slurmd.pid
SlurmdPort=6818
SlurmdSpoolDir=/var/spool/slurm
SlurmUser=slurm
StateSaveLocation=/var/lib/slurm

#
# Process Tracking
#
ProctrackType=proctrack/linuxproc
TaskPlugin=task/affinity

#
# Timers
#
InactiveLimit=0
KillWait=30
MinJobAge=300
SlurmctldTimeout=120
SlurmdTimeout=300
Waittime=0

#
# Scheduling
#
SchedulerType=sched/backfill
SelectType=select/cons_tres

#
# Node Overrides (simulation)
#
SlurmdParameters=config_overrides

#
# Priority - Multifactor
#
PriorityType=priority/multifactor
PriorityDecayHalfLife=7-0
PriorityFavorSmall=NO
PriorityMaxAge=7-0
PriorityUsageResetPeriod=MONTHLY
PriorityWeightAge=1000
PriorityWeightFairshare=10000
PriorityWeightJobSize=500
PriorityWeightPartition=1000
PriorityWeightQOS=2000
AccountingStorageEnforce=associations,limits,qos

#
# Service Behavior
#
ReturnToService=2

#
# Accounting
#
AccountingStorageHost=slurmdbd
AccountingStorageType=accounting_storage/slurmdbd
JobCompLoc=/var/log/slurm/jobcomp.log
JobCompType=jobcomp/filetxt
JobAcctGatherType=jobacct_gather/linux
JobAcctGatherFrequency=30

#
# Logging
#
SlurmctldDebug=info
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdDebug=info
SlurmdLogFile=/var/log/slurm/slurmd.log

#
# Compute Nodes (simulation scale)
#
NodeName={node_range} CPUs={cpus_per_node} RealMemory={memory_per_node} State=UNKNOWN

#
# Partitions
#
PartitionName=normal Nodes={node_range} Default=YES MaxTime=INFINITE State=UP
"""


def _compress_node_range(names: list[str]) -> str:
    """Compress ['c1','c2','c3'] into 'c[1-3]'."""
    # Group by prefix
    prefixes: dict[str, list[int]] = {}
    for name in sorted(names):
        prefix = name.rstrip("0123456789")
        num = name[len(prefix):]
        if num.isdigit():
            prefixes.setdefault(prefix, []).append(int(num))
        else:
            prefixes.setdefault(name, [])

    parts = []
    for prefix, nums in sorted(prefixes.items()):
        if not nums:
            parts.append(prefix)
        elif len(nums) == 1:
            parts.append(f"{prefix}{nums[0]}")
        else:
            nums.sort()
            parts.append(f"{prefix}[{nums[0]}-{nums[-1]}]")

    return ",".join(parts)


# ── Phase implementations ──────────────────────────────────────────

def phase_create_users(progress, task_id) -> tuple[bool, str]:
    """Phase 1: Create Unix users in all containers."""
    users = get_all_users()
    containers = ["slurmctld"] + get_running_compute_nodes()

    if not containers:
        return False, "No running containers found"

    # Build a single useradd script for efficiency
    useradd_cmds = []
    for user in users:
        useradd_cmds.append(
            f"id {user} &>/dev/null || useradd -m -s /bin/bash {user}"
        )
    batch_script = " && ".join(useradd_cmds)

    for container in containers:
        progress.update(task_id, description=f"Creating users in {container}...")
        result = run_in_container(container, batch_script)
        if result.returncode != 0:
            # Try individually if batch fails
            for user in users:
                run_in_container(
                    container,
                    f"id {user} &>/dev/null || useradd -m -s /bin/bash {user}",
                )
        progress.advance(task_id)

    return True, f"Created {len(users)} users across {len(containers)} containers"


def phase_setup_accounting(progress, task_id) -> tuple[bool, str]:
    """Phase 2: Set up Slurm accounts, users, and QOS."""
    # Add cluster to accounting (idempotent)
    run_in_slurmctld(
        "sacctmgr -i add cluster linux 2>/dev/null || true"
    )
    progress.advance(task_id)

    # Create QOS tiers
    progress.update(task_id, description="Creating QOS tiers...")
    for qos in QOS_TIERS:
        run_in_slurmctld(
            f"sacctmgr -i add qos {qos['name']} "
            f"Priority={qos['priority']} "
            f"MaxSubmitJobsPerUser={qos['max_submit']} "
            f"2>/dev/null || "
            f"sacctmgr -i modify qos {qos['name']} set "
            f"Priority={qos['priority']} "
            f"MaxSubmitJobsPerUser={qos['max_submit']}"
        )
    progress.advance(task_id)

    # Create a root account first
    progress.update(task_id, description="Creating root account...")
    run_in_slurmctld(
        "sacctmgr -i add account root Description='Root account' Organization='Simulation' 2>/dev/null || true"
    )
    progress.advance(task_id)

    # Create accounts and users
    qos_list = ",".join(q["name"] for q in QOS_TIERS)

    for acct in ACCOUNTS:
        progress.update(task_id, description=f"Setting up account: {acct['name']}...")

        # Create account under root
        run_in_slurmctld(
            f"sacctmgr -i add account {acct['name']} "
            f"parent=root "
            f"Description='{acct['name'].title()} department' "
            f"Organization='Simulation' "
            f"Fairshare={acct['shares']} "
            f"2>/dev/null || "
            f"sacctmgr -i modify account {acct['name']} set "
            f"Fairshare={acct['shares']}"
        )

        # Add users to account with QOS access
        for user in acct["users"]:
            run_in_slurmctld(
                f"sacctmgr -i add user {user} "
                f"Account={acct['name']} "
                f"DefaultQOS=normal "
                f"QOS={qos_list} "
                f"2>/dev/null || true"
            )

        progress.advance(task_id)

    return True, f"Created {len(ACCOUNTS)} accounts, {len(get_all_users())} users, {len(QOS_TIERS)} QOS tiers"


def phase_scale_nodes(progress, task_id) -> tuple[bool, str]:
    """Phase 3: Update slurm.conf for simulation scale."""
    compute_nodes = get_running_compute_nodes()
    if not compute_nodes:
        return False, "No compute nodes found"

    progress.update(task_id, description="Generating simulation slurm.conf...")
    cpus_per_node = 1000
    conf_content = generate_simulation_slurm_conf(compute_nodes, cpus_per_node)

    # Write to config directory
    config_path = PROJECT_DIR / "config" / "25.05" / "slurm.conf"
    config_path.write_text(conf_content)
    progress.advance(task_id)

    # Apply config
    progress.update(task_id, description="Applying configuration (scontrol reconfigure)...")
    result = run_in_slurmctld("scontrol reconfigure")
    progress.advance(task_id)

    # Wait for nodes to register with new config
    progress.update(task_id, description="Waiting for nodes to register...")
    for _ in range(15):
        result = run_in_slurmctld("sinfo -h -o '%T' | grep -c idle", check=False)
        if result.returncode == 0 and result.stdout.strip().isdigit():
            idle = int(result.stdout.strip())
            if idle > 0:
                break
        time.sleep(2)
    progress.advance(task_id)

    total_slots = len(compute_nodes) * cpus_per_node
    return True, (
        f"{len(compute_nodes)} nodes × {cpus_per_node} CPUs = "
        f"{total_slots:,} total job slots"
    )


def phase_submit_jobs(progress, task_id) -> tuple[bool, str]:
    """Phase 4: Submit ~30,000 jobs distributed across users."""
    total_submitted = 0
    total_target = 0

    # Calculate target jobs per user
    user_jobs: list[tuple[str, str, int, str]] = []  # (user, account, count, qos)
    for acct in ACCOUNTS:
        lo, hi = PROFILE_JOBS[acct["profile"]]
        for user in acct["users"]:
            count = random.randint(lo, hi)
            # Pick a QOS based on weights
            qos = random.choices(
                list(QOS_WEIGHTS.keys()),
                weights=list(QOS_WEIGHTS.values()),
                k=1,
            )[0]
            user_jobs.append((user, acct["name"], count, qos))
            total_target += count

    progress.update(task_id, total=len(user_jobs))

    for user, account, count, qos in user_jobs:
        # Random job duration between 5-60 minutes
        duration_min = random.randint(5, 60)
        job_name = f"sim_{account}_{user}"

        progress.update(
            task_id,
            description=f"Submitting {count} jobs as {user} ({account})...",
        )

        # Use job array for efficiency: one sbatch = many tasks
        # Slurm MaxArraySize default is 1001, so split if needed
        remaining = count
        while remaining > 0:
            batch = min(remaining, 1000)
            array_spec = f"1-{batch}"

            script = f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --account={account}
#SBATCH --qos={qos}
#SBATCH --array={array_spec}
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time={duration_min}
#SBATCH --output=/dev/null

sleep {duration_min * 60}
"""
            # Submit as the user via su
            escaped_script = script.replace("'", "'\\''")
            cmd = (
                f"cat > /tmp/sim_job_{user}.sh << 'SIMJOB'\n"
                f"{script}"
                f"SIMJOB\n"
                f"chmod 644 /tmp/sim_job_{user}.sh && "
                f"su - {user} -s /bin/bash -c 'sbatch --parsable /tmp/sim_job_{user}.sh' 2>/dev/null"
            )

            result = run_in_slurmctld(cmd)
            if result.returncode == 0 and result.stdout.strip():
                total_submitted += batch
            else:
                # If su-based submission fails, try with --uid
                cmd_fallback = (
                    f"sbatch --parsable --uid={user} "
                    f"--account={account} --qos={qos} "
                    f"--job-name={job_name} "
                    f"--array={array_spec} "
                    f"--ntasks=1 --cpus-per-task=1 "
                    f"--time={duration_min} "
                    f"--output=/dev/null "
                    f"--wrap='sleep {duration_min * 60}'"
                )
                result2 = run_in_slurmctld(cmd_fallback)
                if result2.returncode == 0 and result2.stdout.strip():
                    total_submitted += batch

            remaining -= batch

        progress.advance(task_id)

    return True, f"Submitted {total_submitted:,} / {total_target:,} target jobs"


# ── Teardown ────────────────────────────────────────────────────────

def teardown_simulation(progress, task_id) -> tuple[bool, str]:
    """Remove all simulation state."""
    users = get_all_users()

    # Cancel all jobs
    progress.update(task_id, description="Cancelling all jobs...")
    run_in_slurmctld("scancel --all 2>/dev/null || true")
    # Also cancel per-user in case --all doesn't catch everything
    for user in users:
        run_in_slurmctld(f"scancel -u {user} 2>/dev/null || true")
    progress.advance(task_id)

    # Wait for jobs to clear
    progress.update(task_id, description="Waiting for jobs to clear...")
    for _ in range(10):
        result = run_in_slurmctld("squeue -h | wc -l", check=False)
        if result.returncode == 0 and result.stdout.strip() == "0":
            break
        time.sleep(2)
    progress.advance(task_id)

    # Remove users from accounting
    progress.update(task_id, description="Removing Slurm accounting entries...")
    for user in users:
        run_in_slurmctld(f"sacctmgr -i delete user {user} 2>/dev/null || true")
    progress.advance(task_id)

    # Remove accounts
    progress.update(task_id, description="Removing accounts...")
    for acct in reversed(ACCOUNTS):
        run_in_slurmctld(f"sacctmgr -i delete account {acct['name']} 2>/dev/null || true")
    run_in_slurmctld("sacctmgr -i delete account root 2>/dev/null || true")
    progress.advance(task_id)

    # Remove QOS tiers
    progress.update(task_id, description="Removing QOS tiers...")
    for qos in QOS_TIERS:
        run_in_slurmctld(f"sacctmgr -i delete qos {qos['name']} 2>/dev/null || true")
    progress.advance(task_id)

    # Remove Unix users from containers
    progress.update(task_id, description="Removing Unix users...")
    containers = ["slurmctld"] + get_running_compute_nodes()
    userdel_cmds = " ; ".join(f"userdel -r {u} 2>/dev/null || true" for u in users)
    for container in containers:
        run_in_container(container, userdel_cmds)
    progress.advance(task_id)

    # Restore default slurm.conf (2-node minimal)
    progress.update(task_id, description="Restoring default slurm.conf...")
    from .scale import generate_slurm_conf, write_slurm_conf, apply_config
    default_conf = generate_slurm_conf(standard=2)
    write_slurm_conf(default_conf)
    apply_config()
    progress.advance(task_id)

    return True, "Simulation fully cleaned up, cluster restored to default 2-node config"


# ── CLI Commands ────────────────────────────────────────────────────

@click.group()
def simulate():
    """Set up and tear down large-scale priority simulations.

    \b
    Creates a realistic HPC environment with ~50 users, ~15 accounts,
    and ~30,000 jobs to exercise the priority dashboard.

    \b
    Quick start:
      playground simulate setup       # Build full simulation (~2 min)
      playground priority live         # Watch the priority dashboard
      playground simulate teardown     # Clean everything up

    \b
    See also:
      playground/docs/priority-simulation.md
    """
    pass


@simulate.command()
@click.option(
    "--jobs-scale",
    default=1.0,
    type=float,
    help="Scale factor for job count (0.5 = half, 2.0 = double). Default 1.0 ≈ 30k jobs.",
)
@click.option(
    "--cpus-per-node",
    default=1000,
    type=int,
    help="Virtual CPUs per compute node (controls running vs pending ratio).",
)
@click.option(
    "--seed",
    default=None,
    type=int,
    help="Random seed for reproducible job distribution.",
)
def setup(jobs_scale, cpus_per_node, seed):
    """Set up the full priority simulation.

    Creates Unix users, configures Slurm accounting with 15 accounts and
    fairshare weights, scales nodes for simulation, and submits ~30,000
    jobs distributed across 50 users with varying QOS levels.

    The resulting cluster will have ~5,000 running jobs and ~25,000
    pending jobs, with realistic priority/fairshare divergence.
    """
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running. Start with:[/yellow]")
        console.print("  [cyan]make up[/cyan]  or  [cyan]make playground-start[/cyan]")
        return

    if seed is not None:
        random.seed(seed)

    if jobs_scale != 1.0:
        # Adjust job counts
        for profile in PROFILE_JOBS:
            lo, hi = PROFILE_JOBS[profile]
            PROFILE_JOBS[profile] = (int(lo * jobs_scale), int(hi * jobs_scale))

    console.print("\n[bold blue]━━━ Priority Simulation Setup ━━━[/bold blue]\n")

    # Show what we're about to do
    total_users = len(get_all_users())
    total_accounts = len(ACCOUNTS)
    est_jobs = sum(
        sum(PROFILE_JOBS[a["profile"]]) // 2 * len(a["users"])
        for a in ACCOUNTS
    )
    compute_nodes = get_running_compute_nodes()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Users", str(total_users))
    table.add_row("Accounts", str(total_accounts))
    table.add_row("QOS tiers", str(len(QOS_TIERS)))
    table.add_row("Est. jobs", f"~{est_jobs:,}")
    table.add_row("Compute nodes", str(len(compute_nodes)))
    table.add_row("CPUs/node", f"{cpus_per_node:,}")
    table.add_row("Total job slots", f"{len(compute_nodes) * cpus_per_node:,}")
    console.print(table)
    console.print()

    phases = [
        ("Phase 1: Create Unix users",     phase_create_users,     len(["slurmctld"] + compute_nodes)),
        ("Phase 2: Configure accounting",   phase_setup_accounting, len(ACCOUNTS) + 3),
        ("Phase 3: Scale nodes",            phase_scale_nodes,      3),
        ("Phase 4: Submit jobs",            phase_submit_jobs,      0),  # set dynamically
    ]

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for name, func, total in phases:
            tid = progress.add_task(name, total=total or 1)
            ok, msg = func(progress, tid)
            progress.update(tid, description=f"[green]✓[/green] {name}")
            progress.update(tid, completed=progress.tasks[tid].total)
            results.append((name, ok, msg))

    console.print()
    console.print("[bold blue]━━━ Setup Complete ━━━[/bold blue]\n")

    for name, ok, msg in results:
        status = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {status} {name}: {msg}")

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  [cyan]playground priority live[/cyan]          # Watch the priority dashboard")
    console.print("  [cyan]playground priority live -u user01[/cyan] # Highlight a specific user")
    console.print("  [cyan]playground priority show[/cyan]          # One-shot snapshot")
    console.print("  [cyan]playground priority fairshare[/cyan]     # Fairshare table")
    console.print("  [cyan]playground simulate teardown[/cyan]      # Clean up when done")
    console.print()


@simulate.command()
def teardown():
    """Tear down the simulation and restore default cluster.

    Cancels all jobs, removes accounting entries (accounts, users, QOS),
    deletes Unix users from containers, and restores the default 2-node
    slurm.conf.
    """
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    console.print("\n[bold blue]━━━ Priority Simulation Teardown ━━━[/bold blue]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        tid = progress.add_task("Tearing down simulation...", total=7)
        ok, msg = teardown_simulation(progress, tid)
        progress.update(tid, description="[green]✓[/green] Teardown complete")

    console.print()
    if ok:
        console.print(f"  [green]✓[/green] {msg}")
    else:
        console.print(f"  [red]✗[/red] {msg}")
    console.print()


@simulate.command()
def status():
    """Show current simulation status."""
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    console.print("\n[bold blue]━━━ Simulation Status ━━━[/bold blue]\n")

    # Check if simulation accounts exist
    result = run_in_slurmctld(
        "sacctmgr -n -P list account format=Account,Description,Fairshare",
        check=False,
    )

    sim_accounts = []
    acct_names = {a["name"] for a in ACCOUNTS}
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            parts = line.split("|")
            if len(parts) >= 3 and parts[0] in acct_names:
                sim_accounts.append({
                    "name": parts[0],
                    "description": parts[1],
                    "shares": parts[2],
                })

    if not sim_accounts:
        console.print("  [dim]No simulation detected. Run:[/dim]")
        console.print("    [cyan]playground simulate setup[/cyan]")
        return

    console.print(f"  [green]Simulation active[/green]: {len(sim_accounts)}/{len(ACCOUNTS)} accounts found\n")

    # Job stats
    result = run_in_slurmctld(
        "squeue -h -o '%T' | sort | uniq -c | sort -rn",
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        console.print("  [bold]Job Queue:[/bold]")
        for line in result.stdout.strip().split("\n"):
            console.print(f"    {line.strip()}")
        console.print()

    # Node stats
    result = run_in_slurmctld("sinfo -h -o '%C'", check=False)
    if result.returncode == 0 and result.stdout.strip():
        cpus = result.stdout.strip().split("\n")[0]
        console.print(f"  [bold]CPUs[/bold] (alloc/idle/other/total): {cpus}")

    console.print()
