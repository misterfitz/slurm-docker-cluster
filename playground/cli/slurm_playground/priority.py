"""Priority and fairshare TUI for Slurm Playground.

Provides a live terminal dashboard showing job prioritization,
fairshare values, queue position, and priority factor breakdowns.
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

SCRIPT_DIR = Path(__file__).parent
CLI_DIR = SCRIPT_DIR.parent
PLAYGROUND_DIR = CLI_DIR.parent
PROJECT_DIR = PLAYGROUND_DIR.parent


def get_docker_compose_cmd():
    """Get the docker compose command."""
    try:
        subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=True
        )
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose"]


def run_in_slurmctld(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command inside the slurmctld container."""
    compose_cmd = get_docker_compose_cmd()
    full_cmd = compose_cmd + [
        "-f",
        str(PROJECT_DIR / "docker-compose.yml"),
        "exec",
        "-T",
        "slurmctld",
        "bash",
        "-c",
        cmd,
    ]
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)


def is_cluster_running() -> bool:
    """Check if the Slurm cluster is running."""
    compose_cmd = get_docker_compose_cmd()
    result = subprocess.run(
        compose_cmd
        + [
            "-f",
            str(PROJECT_DIR / "docker-compose.yml"),
            "ps",
            "slurmctld",
            "--status",
            "running",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def get_fairshare_data() -> list[dict]:
    """Get fairshare data from sshare for all accounts/users."""
    entries = []
    result = run_in_slurmctld(
        "sshare -a -P -l --format=Account,User,RawShares,NormShares,"
        "RawUsage,NormUsage,EffectvUsage,FairShare,LevelFS",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return entries

    lines = result.stdout.strip().split("\n")
    if len(lines) < 2:
        return entries

    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 9:
            continue
        account = parts[0].strip()
        user = parts[1].strip()
        if not account and not user:
            continue
        entries.append({
            "account": account or "(root)",
            "user": user or "(account total)",
            "raw_shares": parts[2].strip(),
            "norm_shares": _safe_float(parts[3]),
            "raw_usage": _safe_int(parts[4]),
            "norm_usage": _safe_float(parts[5]),
            "effectv_usage": _safe_float(parts[6]),
            "fairshare": _safe_float(parts[7]),
            "level_fs": parts[8].strip(),
        })
    return entries


def get_priority_factors() -> list[dict]:
    """Get priority factor breakdown from sprio for all pending/running jobs."""
    jobs = []
    result = run_in_slurmctld(
        "sprio -l -h --format='%i|%u|%a|%A|%F|%J|%P|%Q|%Y|%T' 2>/dev/null",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        # Try simpler format if -l isn't supported
        result = run_in_slurmctld(
            "sprio -h --format='%i|%u|%Y|%A|%F|%J|%P|%Q' 2>/dev/null",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return jobs

    for line in result.stdout.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) >= 8:
            jobs.append({
                "job_id": parts[0].strip(),
                "user": parts[1].strip(),
                "priority": _safe_float(parts[2]) if len(parts) <= 8 else _safe_float(parts[8]),
                "age": _safe_float(parts[3] if len(parts) <= 8 else parts[2]),
                "fairshare": _safe_float(parts[4] if len(parts) <= 8 else parts[3]),
                "jobsize": _safe_float(parts[5] if len(parts) <= 8 else parts[4]),
                "partition": _safe_float(parts[6] if len(parts) <= 8 else parts[5]),
                "qos": _safe_float(parts[7] if len(parts) <= 8 else parts[6]),
            })
    return jobs


def get_queue_by_account() -> list[dict]:
    """Get job queue grouped by account and user with state info."""
    entries = []
    result = run_in_slurmctld(
        "squeue -h -o '%A|%u|%a|%T|%p|%Q|%r|%V|%j' --sort=-p",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return entries

    for line in result.stdout.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) >= 9:
            entries.append({
                "job_id": parts[0].strip(),
                "user": parts[1].strip(),
                "account": parts[2].strip(),
                "state": parts[3].strip(),
                "priority_val": parts[4].strip(),
                "priority_num": _safe_float(parts[5]),
                "reason": parts[6].strip(),
                "submit_time": parts[7].strip(),
                "name": parts[8].strip(),
            })
    return entries


def get_priority_config() -> dict:
    """Get the priority weight configuration from scontrol."""
    config = {}
    result = run_in_slurmctld(
        "scontrol show config | grep -i 'Priority'",
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                key, _, val = line.partition("=")
                config[key.strip()] = val.strip()
    return config


def _safe_float(val: str) -> float:
    try:
        return float(val.strip())
    except (ValueError, AttributeError):
        return 0.0


def _safe_int(val: str) -> int:
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return 0


def _bar(value: float, max_val: float, width: int = 15) -> str:
    """Render a mini bar chart."""
    if max_val <= 0:
        return "░" * width
    ratio = min(value / max_val, 1.0)
    filled = int(width * ratio)
    return "█" * filled + "░" * (width - filled)


def _fairshare_style(fs: float) -> str:
    """Color style based on fairshare value."""
    if fs >= 0.8:
        return "bold green"
    elif fs >= 0.5:
        return "green"
    elif fs >= 0.3:
        return "yellow"
    elif fs >= 0.1:
        return "rgb(255,165,0)"
    else:
        return "red"


def _state_style(state: str) -> str:
    """Color style for job state."""
    s = state.upper()
    if s in ("RUNNING", "R"):
        return "green"
    elif s in ("PENDING", "PD"):
        return "yellow"
    elif s in ("COMPLETING", "CG"):
        return "cyan"
    else:
        return "dim"


def build_priority_dashboard(
    highlight_user: str | None = None,
    highlight_account: str | None = None,
) -> Panel:
    """Build the full priority TUI dashboard."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    output = Text()

    # ── Section 1: Fairshare by Account/User ──
    fairshare = get_fairshare_data()
    output.append("Fairshare by Account / User", style="bold cyan")
    output.append(f"  ({timestamp})\n", style="dim")

    if fairshare:
        max_usage = max((e["raw_usage"] for e in fairshare), default=1) or 1
        fs_table = Table(
            show_header=True,
            header_style="bold",
            box=None,
            padding=(0, 1),
            expand=True,
        )
        fs_table.add_column("Account", min_width=12)
        fs_table.add_column("User", min_width=10)
        fs_table.add_column("Shares", justify="right", min_width=6)
        fs_table.add_column("FairShare", justify="right", min_width=8)
        fs_table.add_column("", min_width=15)  # bar
        fs_table.add_column("RawUsage", justify="right", min_width=10)
        fs_table.add_column("EffUsage", justify="right", min_width=8)
        fs_table.add_column("LevelFS", justify="right", min_width=8)

        for e in fairshare:
            is_hl = (
                (highlight_user and e["user"] == highlight_user)
                or (highlight_account and e["account"] == highlight_account)
            )
            row_style = "bold reverse" if is_hl else ""
            fs_style = _fairshare_style(e["fairshare"])
            bar = _bar(e["fairshare"], 1.0)

            fs_table.add_row(
                e["account"],
                e["user"],
                e["raw_shares"],
                f"[{fs_style}]{e['fairshare']:.4f}[/{fs_style}]",
                f"[{fs_style}]{bar}[/{fs_style}]",
                f"{e['raw_usage']:,}",
                f"{e['effectv_usage']:.4f}",
                e["level_fs"],
                style=row_style,
            )

        # We can't directly append a Table to Text, so we'll render sections separately
        # Instead, return a group
    else:
        output.append("  No fairshare data (is PriorityType=priority/multifactor set?)\n", style="dim")

    # ── Section 2: Job Queue with Priority ──
    queue = get_queue_by_account()

    # ── Section 3: Priority Factor Breakdown ──
    factors = get_priority_factors()

    # ── Section 4: Priority Config ──
    config = get_priority_config()

    # Build using console group for mixed tables/text
    from rich.console import Group

    sections = []

    # --- Fairshare section ---
    sections.append(Text.assemble(
        ("Fairshare by Account / User", "bold cyan"),
        (f"  {timestamp}\n", "dim"),
    ))
    if fairshare:
        sections.append(fs_table)
    else:
        sections.append(Text("  No fairshare data. Set PriorityType=priority/multifactor.\n", style="dim"))

    sections.append(Text(""))

    # --- Queue section ---
    sections.append(Text("Job Queue  (sorted by priority)\n", style="bold cyan"))
    if queue:
        q_table = Table(
            show_header=True,
            header_style="bold",
            box=None,
            padding=(0, 1),
            expand=True,
        )
        q_table.add_column("#", justify="right", min_width=3)
        q_table.add_column("JobID", min_width=6)
        q_table.add_column("Name", min_width=10, max_width=18)
        q_table.add_column("User", min_width=8)
        q_table.add_column("Account", min_width=10)
        q_table.add_column("State", min_width=7)
        q_table.add_column("Priority", justify="right", min_width=8)
        q_table.add_column("Reason", min_width=12, max_width=20)

        pending_rank = 0
        for entry in queue:
            is_pending = entry["state"].upper() in ("PENDING", "PD")
            if is_pending:
                pending_rank += 1
                rank_str = str(pending_rank)
            else:
                rank_str = "-"

            is_hl = (
                (highlight_user and entry["user"] == highlight_user)
                or (highlight_account and entry["account"] == highlight_account)
            )
            row_style = "bold reverse" if is_hl else ""
            st_style = _state_style(entry["state"])

            q_table.add_row(
                rank_str,
                entry["job_id"],
                entry["name"],
                entry["user"],
                entry["account"],
                f"[{st_style}]{entry['state']}[/{st_style}]",
                f"{entry['priority_num']:.0f}",
                entry["reason"] if entry["reason"] != "None" else "",
                style=row_style,
            )

        sections.append(q_table)

        # Summary counts
        running = sum(1 for e in queue if e["state"].upper() in ("RUNNING", "R"))
        pending = sum(1 for e in queue if e["state"].upper() in ("PENDING", "PD"))
        sections.append(Text.assemble(
            ("\n  Running: ", "dim"),
            (str(running), "green"),
            ("  Pending: ", "dim"),
            (str(pending), "yellow"),
            ("  Total: ", "dim"),
            (str(len(queue)), ""),
        ))
    else:
        sections.append(Text("  No jobs in queue\n", style="dim"))

    sections.append(Text(""))

    # --- Priority factor breakdown ---
    sections.append(Text("Priority Factor Breakdown  (pending jobs)\n", style="bold cyan"))
    if factors:
        max_prio = max((f["priority"] for f in factors), default=1) or 1
        p_table = Table(
            show_header=True,
            header_style="bold",
            box=None,
            padding=(0, 1),
            expand=True,
        )
        p_table.add_column("JobID", min_width=6)
        p_table.add_column("User", min_width=8)
        p_table.add_column("Priority", justify="right", min_width=8)
        p_table.add_column("", min_width=15)  # bar
        p_table.add_column("Age", justify="right", min_width=6)
        p_table.add_column("FairShr", justify="right", min_width=7)
        p_table.add_column("JobSize", justify="right", min_width=7)
        p_table.add_column("Partition", justify="right", min_width=9)
        p_table.add_column("QOS", justify="right", min_width=5)
        p_table.add_column("Biggest Factor", min_width=14)

        for f in sorted(factors, key=lambda x: x["priority"], reverse=True):
            is_hl = highlight_user and f["user"] == highlight_user
            row_style = "bold reverse" if is_hl else ""
            bar = _bar(f["priority"], max_prio)

            # Find dominant factor
            factor_vals = {
                "Age": f["age"],
                "FairShare": f["fairshare"],
                "JobSize": f["jobsize"],
                "Partition": f["partition"],
                "QOS": f["qos"],
            }
            biggest = max(factor_vals, key=factor_vals.get)
            biggest_pct = (
                f"{factor_vals[biggest] / f['priority'] * 100:.0f}%"
                if f["priority"] > 0 else "-"
            )

            p_table.add_row(
                f["job_id"],
                f["user"],
                f"{f['priority']:.0f}",
                bar,
                f"{f['age']:.0f}",
                f"{f['fairshare']:.0f}",
                f"{f['jobsize']:.0f}",
                f"{f['partition']:.0f}",
                f"{f['qos']:.0f}",
                f"{biggest} ({biggest_pct})",
                style=row_style,
            )

        sections.append(p_table)
    else:
        sections.append(Text("  No pending jobs with priority data\n", style="dim"))

    sections.append(Text(""))

    # --- Config summary ---
    sections.append(Text("Priority Weights (active config)\n", style="bold cyan"))
    weight_keys = [
        ("PriorityWeightAge", "Age"),
        ("PriorityWeightFairshare", "Fairshare"),
        ("PriorityWeightJobSize", "JobSize"),
        ("PriorityWeightPartition", "Partition"),
        ("PriorityWeightQOS", "QOS"),
    ]
    config_parts = []
    for key, label in weight_keys:
        val = config.get(key, "?")
        config_parts.append(f"  {label}: {val}")
    decay = config.get("PriorityDecayHalfLife", "?")
    max_age = config.get("PriorityMaxAge", "?")
    config_parts.append(f"  Decay½Life: {decay}")
    config_parts.append(f"  MaxAge: {max_age}")
    sections.append(Text("  ".join(config_parts) + "\n", style="dim"))

    return Panel(
        Group(*sections),
        title="[bold] Slurm Priority Dashboard [/bold]",
        border_style="blue",
        padding=(1, 2),
    )


# ── CLI Commands ──


@click.group()
def priority():
    """View job priority, fairshare, and queue ranking.

    \b
    Examples:
      playground priority live              # Real-time priority TUI
      playground priority live -u admin     # Highlight a specific user
      playground priority show              # One-shot snapshot
      playground priority fairshare         # Fairshare table only
      playground priority factors           # Priority factor breakdown
    """
    pass


@priority.command()
@click.option("-u", "--user", default=None, help="Highlight this user's jobs")
@click.option("-a", "--account", default=None, help="Highlight this account's jobs")
@click.option("-r", "--refresh", default=3, help="Refresh interval in seconds")
def live(user, account, refresh):
    """Real-time priority dashboard with fairshare, queue rank, and factor breakdown."""
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    hl_parts = []
    if user:
        hl_parts.append(f"user={user}")
    if account:
        hl_parts.append(f"account={account}")
    hl_msg = f"  Highlighting: {', '.join(hl_parts)}" if hl_parts else ""

    console.print(f"[dim]Press Ctrl+C to exit. Refreshing every {refresh}s.{hl_msg}[/dim]\n")

    try:
        with Live(
            build_priority_dashboard(highlight_user=user, highlight_account=account),
            console=console,
            refresh_per_second=1,
        ) as live_display:
            while True:
                time.sleep(refresh)
                live_display.update(
                    build_priority_dashboard(
                        highlight_user=user, highlight_account=account
                    )
                )
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped[/dim]")


@priority.command()
@click.option("-u", "--user", default=None, help="Highlight this user's jobs")
@click.option("-a", "--account", default=None, help="Highlight this account's jobs")
def show(user, account):
    """Show a one-shot snapshot of the priority dashboard."""
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    console.print(build_priority_dashboard(highlight_user=user, highlight_account=account))


@priority.command()
def fairshare():
    """Show fairshare values for all accounts and users."""
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    console.print("\n[bold blue]=== Fairshare Report ===[/bold blue]\n")

    entries = get_fairshare_data()
    if not entries:
        console.print("[dim]No fairshare data. Is PriorityType=priority/multifactor configured?[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Account")
    table.add_column("User")
    table.add_column("RawShares", justify="right")
    table.add_column("FairShare", justify="right")
    table.add_column("", min_width=15)
    table.add_column("RawUsage", justify="right")
    table.add_column("EffUsage", justify="right")
    table.add_column("LevelFS", justify="right")

    for e in entries:
        fs_style = _fairshare_style(e["fairshare"])
        bar = _bar(e["fairshare"], 1.0)
        table.add_row(
            e["account"],
            e["user"],
            e["raw_shares"],
            f"[{fs_style}]{e['fairshare']:.4f}[/{fs_style}]",
            f"[{fs_style}]{bar}[/{fs_style}]",
            f"{e['raw_usage']:,}",
            f"{e['effectv_usage']:.4f}",
            e["level_fs"],
        )

    console.print(table)
    console.print()


@priority.command()
@click.option("-u", "--user", default=None, help="Filter to a specific user")
def factors(user):
    """Show priority factor breakdown for pending jobs."""
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    console.print("\n[bold blue]=== Priority Factor Breakdown ===[/bold blue]\n")

    data = get_priority_factors()
    if not data:
        console.print("[dim]No pending jobs with priority data.[/dim]")
        return

    if user:
        data = [f for f in data if f["user"] == user]
        if not data:
            console.print(f"[dim]No pending jobs for user '{user}'[/dim]")
            return

    data.sort(key=lambda x: x["priority"], reverse=True)
    max_prio = max((f["priority"] for f in data), default=1) or 1

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Rank", justify="right")
    table.add_column("JobID")
    table.add_column("User")
    table.add_column("Total Priority", justify="right")
    table.add_column("", min_width=15)
    table.add_column("Age", justify="right")
    table.add_column("FairShare", justify="right")
    table.add_column("JobSize", justify="right")
    table.add_column("Partition", justify="right")
    table.add_column("QOS", justify="right")
    table.add_column("Dominant Factor")

    for rank, f in enumerate(data, 1):
        bar = _bar(f["priority"], max_prio)
        factor_vals = {
            "Age": f["age"],
            "FairShare": f["fairshare"],
            "JobSize": f["jobsize"],
            "Partition": f["partition"],
            "QOS": f["qos"],
        }
        biggest = max(factor_vals, key=factor_vals.get)
        biggest_pct = (
            f"{factor_vals[biggest] / f['priority'] * 100:.0f}%"
            if f["priority"] > 0 else "-"
        )

        table.add_row(
            str(rank),
            f["job_id"],
            f["user"],
            f"{f['priority']:.0f}",
            bar,
            f"{f['age']:.0f}",
            f"{f['fairshare']:.0f}",
            f"{f['jobsize']:.0f}",
            f"{f['partition']:.0f}",
            f"{f['qos']:.0f}",
            f"{biggest} ({biggest_pct})",
        )

    console.print(table)

    # Show weight context
    config = get_priority_config()
    console.print("\n[bold]Active Priority Weights:[/bold]")
    for key in ("PriorityWeightAge", "PriorityWeightFairshare",
                "PriorityWeightJobSize", "PriorityWeightPartition", "PriorityWeightQOS"):
        val = config.get(key, "not set")
        label = key.replace("PriorityWeight", "")
        console.print(f"  {label:<12} {val}")
    console.print()


@priority.command()
@click.argument("job_id")
def explain(job_id):
    """Explain the priority calculation for a specific job.

    Shows each factor's contribution, the weights applied, and where
    the job sits relative to others in the queue.
    """
    if not is_cluster_running():
        console.print("[yellow]Cluster is not running.[/yellow]")
        return

    console.print(f"\n[bold blue]=== Priority Explanation: Job {job_id} ===[/bold blue]\n")

    # Get this job's priority factors
    result = run_in_slurmctld(
        f"sprio -j {job_id} -l -h --format='%i|%u|%a|%A|%F|%J|%P|%Q|%Y|%T' 2>/dev/null",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        # Try simpler format
        result = run_in_slurmctld(
            f"sprio -j {job_id} -h --format='%i|%u|%Y|%A|%F|%J|%P|%Q' 2>/dev/null",
            check=False,
        )

    if result.returncode != 0 or not result.stdout.strip():
        console.print(f"[red]No priority data for job {job_id}. Is it pending?[/red]")
        return

    parts = result.stdout.strip().split("|")
    if len(parts) < 8:
        console.print("[red]Unexpected sprio output format[/red]")
        return

    # Parse depending on format
    if len(parts) >= 10:
        job = {
            "job_id": parts[0].strip(), "user": parts[1].strip(),
            "account": parts[2].strip(),
            "age": _safe_float(parts[3]), "fairshare": _safe_float(parts[4]),
            "jobsize": _safe_float(parts[5]), "partition": _safe_float(parts[6]),
            "qos": _safe_float(parts[7]), "priority": _safe_float(parts[8]),
        }
    else:
        job = {
            "job_id": parts[0].strip(), "user": parts[1].strip(),
            "priority": _safe_float(parts[2]),
            "age": _safe_float(parts[3]), "fairshare": _safe_float(parts[4]),
            "jobsize": _safe_float(parts[5]), "partition": _safe_float(parts[6]),
            "qos": _safe_float(parts[7]),
        }

    config = get_priority_config()

    console.print(f"[bold]Job:[/bold]       {job['job_id']}")
    console.print(f"[bold]User:[/bold]      {job['user']}")
    console.print(f"[bold]Priority:[/bold]  {job['priority']:.0f}")
    console.print()

    # Factor breakdown with visual
    factors = [
        ("Age", job["age"], config.get("PriorityWeightAge", "?")),
        ("FairShare", job["fairshare"], config.get("PriorityWeightFairshare", "?")),
        ("JobSize", job["jobsize"], config.get("PriorityWeightJobSize", "?")),
        ("Partition", job["partition"], config.get("PriorityWeightPartition", "?")),
        ("QOS", job["qos"], config.get("PriorityWeightQOS", "?")),
    ]

    total = job["priority"] if job["priority"] > 0 else 1
    max_factor = max(f[1] for f in factors) or 1

    console.print("[bold]Factor Contributions:[/bold]")
    console.print(f"  {'Factor':<12} {'Score':>8}  {'Weight':>8}  {'% of Total':>10}  Bar")
    console.print(f"  {'─' * 12} {'─' * 8}  {'─' * 8}  {'─' * 10}  {'─' * 20}")

    for name, score, weight in factors:
        pct = score / total * 100 if total > 0 else 0
        bar = _bar(score, max_factor, width=20)

        if pct >= 40:
            style = "bold green"
        elif pct >= 20:
            style = "yellow"
        else:
            style = "dim"

        console.print(
            f"  [{style}]{name:<12} {score:>8.0f}  {weight:>8}  {pct:>9.1f}%  {bar}[/{style}]"
        )

    console.print()

    # Queue position
    all_factors = get_priority_factors()
    if all_factors:
        all_factors.sort(key=lambda x: x["priority"], reverse=True)
        position = next(
            (i + 1 for i, f in enumerate(all_factors) if f["job_id"] == str(job_id)),
            None,
        )
        if position:
            console.print(f"[bold]Queue Position:[/bold] {position} of {len(all_factors)} pending jobs")
            if position == 1:
                console.print("  → [green]This job is next to run[/green]")
            elif position <= 3:
                console.print("  → [cyan]Near the front of the queue[/cyan]")
            else:
                ahead = all_factors[0]
                gap = ahead["priority"] - job["priority"]
                console.print(f"  → [yellow]{position - 1} jobs ahead, priority gap to #1: {gap:.0f}[/yellow]")
    console.print()

    # Fairshare context for this user
    fairshare = get_fairshare_data()
    user_fs = [e for e in fairshare if e["user"] == job["user"]]
    if user_fs:
        fs = user_fs[0]
        fs_style = _fairshare_style(fs["fairshare"])
        console.print(f"[bold]User FairShare Context:[/bold]")
        console.print(f"  Account:     {fs['account']}")
        console.print(f"  FairShare:   [{fs_style}]{fs['fairshare']:.4f}[/{fs_style}]  {_bar(fs['fairshare'], 1.0)}")
        console.print(f"  Raw Usage:   {fs['raw_usage']:,}")
        console.print(f"  Eff Usage:   {fs['effectv_usage']:.4f}")
        console.print(f"  Level FS:    {fs['level_fs']}")
        if fs["fairshare"] < 0.3:
            console.print("  → [yellow]Low fairshare — this user has consumed more than their share[/yellow]")
        elif fs["fairshare"] > 0.7:
            console.print("  → [green]High fairshare — this user is under-utilizing their allocation[/green]")
    console.print()


# ── Compact output helpers ──


def _compact_num(n: float) -> str:
    """Format a number compactly: 1234 → 1.2k, 25000 → 25k."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 10_000:
        return f"{n / 1_000:.0f}k"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}k"
    else:
        return f"{n:.0f}"


def _build_watch_line(
    user: str | None = None,
    account: str | None = None,
) -> dict:
    """Build the data dict for the one-liner watch output.

    Returns a dict with all fields so callers can format as text or JSON.
    """
    data: dict = {"timestamp": datetime.now().strftime("%H:%M:%S")}

    # Queue counts
    queue = get_queue_by_account()
    running = sum(1 for j in queue if j["state"].upper() in ("RUNNING", "R"))
    pending = sum(1 for j in queue if j["state"].upper() in ("PENDING", "PD"))
    data["running"] = running
    data["pending"] = pending
    data["total"] = len(queue)

    # Fairshare extremes
    fairshare = get_fairshare_data()
    users_fs = [e for e in fairshare if e["user"] != "(account total)"]
    if users_fs:
        top = max(users_fs, key=lambda e: e["fairshare"])
        low = min(users_fs, key=lambda e: e["fairshare"])
        data["top_fs"] = {
            "user": top["user"], "account": top["account"],
            "fairshare": top["fairshare"],
        }
        data["low_fs"] = {
            "user": low["user"], "account": low["account"],
            "fairshare": low["fairshare"],
        }

    # Next to run (highest priority pending job)
    factors = get_priority_factors()
    if factors:
        factors.sort(key=lambda x: x["priority"], reverse=True)
        best = factors[0]
        data["next_job"] = {"user": best["user"], "job_id": best["job_id"],
                           "priority": best["priority"]}

    # Personal info
    if user:
        user_entry = next((e for e in users_fs if e["user"] == user), None)
        if user_entry:
            data["user"] = {
                "name": user,
                "account": user_entry["account"],
                "fairshare": user_entry["fairshare"],
            }
            # Find queue rank for this user's highest-priority pending job
            user_factors = [f for f in factors if f["user"] == user]
            if user_factors:
                best_user = max(user_factors, key=lambda x: x["priority"])
                rank = next(
                    (i + 1 for i, f in enumerate(factors)
                     if f["job_id"] == best_user["job_id"]),
                    None,
                )
                data["user"]["rank"] = rank
                data["user"]["total_pending"] = pending
                data["user"]["job_id"] = best_user["job_id"]

            # Count this user's jobs by state
            user_jobs = [j for j in queue if j["user"] == user]
            data["user"]["running"] = sum(
                1 for j in user_jobs if j["state"].upper() in ("RUNNING", "R")
            )
            data["user"]["pending"] = sum(
                1 for j in user_jobs if j["state"].upper() in ("PENDING", "PD")
            )

    if account:
        acct_entries = [e for e in fairshare if e["account"] == account
                        and e["user"] != "(account total)"]
        acct_total = next(
            (e for e in fairshare if e["account"] == account
             and e["user"] == "(account total)"),
            None,
        )
        if acct_total or acct_entries:
            data["account"] = {
                "name": account,
                "fairshare": acct_total["fairshare"] if acct_total else 0,
                "users": len(acct_entries),
            }
            acct_jobs = [j for j in queue if j["account"] == account]
            data["account"]["running"] = sum(
                1 for j in acct_jobs if j["state"].upper() in ("RUNNING", "R")
            )
            data["account"]["pending"] = sum(
                1 for j in acct_jobs if j["state"].upper() in ("PENDING", "PD")
            )

    return data


def _format_watch_line(data: dict) -> str:
    """Format the watch data dict as a compact one-liner string."""
    parts = []

    # Cluster summary
    parts.append(
        f"R:{_compact_num(data['running'])} "
        f"P:{_compact_num(data['pending'])}"
    )

    # Personal user info
    if "user" in data:
        u = data["user"]
        fs = u.get("fairshare", 0)
        segment = f"{u['name']} fs:{fs:.2f}"
        if "rank" in u:
            segment += f" #{u['rank']}/{_compact_num(u['total_pending'])}"
        if u.get("running") or u.get("pending"):
            segment += f" (r:{u.get('running', 0)} p:{u.get('pending', 0)})"
        parts.append(segment)

    # Account info
    if "account" in data:
        a = data["account"]
        segment = f"{a['name']} fs:{a['fairshare']:.2f}"
        segment += f" (r:{a.get('running', 0)} p:{a.get('pending', 0)})"
        parts.append(segment)

    # Fairshare extremes
    if "top_fs" in data and "low_fs" in data:
        t = data["top_fs"]
        l = data["low_fs"]
        parts.append(
            f"hi:{t['user']}({t['fairshare']:.2f}) "
            f"lo:{l['user']}({l['fairshare']:.2f})"
        )

    return " | ".join(parts)


def _format_tmux_status(
    data: dict,
    color: bool = False,
    max_width: int = 50,
) -> str:
    """Format data for tmux status bar (very short, optional tmux colors)."""
    parts = []

    # Running/pending
    r = _compact_num(data["running"])
    p = _compact_num(data["pending"])
    if color:
        parts.append(f"#[fg=green]R:{r}#[default] P:{p}")
    else:
        parts.append(f"R:{r} P:{p}")

    # User info (if available)
    if "user" in data:
        u = data["user"]
        fs = u.get("fairshare", 0)

        if fs >= 0.5:
            fs_color = "green"
        elif fs >= 0.3:
            fs_color = "yellow"
        else:
            fs_color = "red"

        if color:
            segment = f"#[fg={fs_color}]fs:{fs:.2f}#[default]"
        else:
            segment = f"fs:{fs:.2f}"

        if "rank" in u:
            segment += f" #{u['rank']}"

        parts.append(segment)

    result = " ".join(parts)

    # Truncate if needed
    # For tmux color strings, we need to measure without the color codes
    if not color and len(result) > max_width:
        result = result[:max_width - 1] + "~"

    return result


# ── Watch & tmux-status CLI commands ──


@priority.command()
@click.option("-u", "--user", default=None, help="Show your personal rank and fairshare")
@click.option("-a", "--account", default=None, help="Show account-level summary")
@click.option("-r", "--refresh", default=5, help="Refresh interval in seconds")
@click.option("--no-loop", is_flag=True, help="Print once and exit")
@click.option(
    "--format", "fmt",
    type=click.Choice(["short", "json"]),
    default="short",
    help="Output format",
)
def watch(user, account, refresh, no_loop, fmt):
    """Compact one-liner that refreshes — perfect for a tmux pane.

    Shows running/pending counts, fairshare extremes, and optionally
    your personal queue position. Designed for narrow terminal splits.

    \b
    Examples:
      playground priority watch                  # Cluster overview
      playground priority watch -u user01        # Personal status
      playground priority watch -u user01 -r 10  # Slower refresh
      playground priority watch --no-loop --format json  # Script-friendly
    """
    if not is_cluster_running():
        if fmt == "json":
            print(json.dumps({"error": "cluster not running"}))
        else:
            print("cluster not running")
        return

    if no_loop:
        data = _build_watch_line(user=user, account=account)
        if fmt == "json":
            print(json.dumps(data, default=str))
        else:
            print(_format_watch_line(data))
        return

    try:
        with Live("", console=console, refresh_per_second=1) as live_display:
            while True:
                data = _build_watch_line(user=user, account=account)
                if fmt == "json":
                    line = json.dumps(data, default=str)
                else:
                    line = _format_watch_line(data)
                live_display.update(Text(line))
                time.sleep(refresh)
    except KeyboardInterrupt:
        pass


@priority.command(name="tmux-status")
@click.option("-u", "--user", default=None, help="Personalize with your queue rank and fairshare")
@click.option("--color", is_flag=True, help="Output tmux color codes (#[fg=...])")
@click.option("--max-width", default=50, help="Max output width (default 50)")
def tmux_status(user, color, max_width):
    """Output a short string for tmux status-right / status-left.

    Designed to be called by tmux periodically. Use the companion
    caching script (playground/tmux/slurm-status.sh) to avoid
    hammering the cluster on every tmux refresh.

    \b
    tmux.conf example:
      set -g status-right '#(playground/tmux/slurm-status.sh -u user01)'
      set -g status-interval 10

    \b
    Examples:
      playground priority tmux-status                 # Plain: R:5k P:25k
      playground priority tmux-status -u user01       # Plain: R:5k P:25k fs:0.82 #3
      playground priority tmux-status -u user01 --color  # With tmux colors
    """
    if not is_cluster_running():
        print("slurm:down")
        return

    data = _build_watch_line(user=user)
    print(_format_tmux_status(data, color=color, max_width=max_width))
