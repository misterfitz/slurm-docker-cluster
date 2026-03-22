#!/usr/bin/env python3
"""Record a demo of the Slurm priority system using synthetic data.

Renders all output modes (TUI, watch, tmux-status, explain) with
realistic simulated data and prints them with theatrical timing
so asciinema captures a polished recording.

Usage:
    asciinema rec demo.cast -c 'python3 playground/demo/record_demo.py'
    agg demo.cast playground/demo/priority-demo.gif --theme monokai --speed 1.5
"""

import sys
import time

sys.path.insert(0, "playground/cli")

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(width=120, force_terminal=True, file=sys.stdout)


def pause(secs=0.8):
    time.sleep(secs)


def type_cmd(cmd, delay=0.03):
    """Simulate typing a command with character-by-character output."""
    console.print()
    sys.stdout.write("\033[1;32m$ \033[0m")
    sys.stdout.flush()
    for ch in cmd:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()
    pause(0.4)


# ── Synthetic data ──────────────────────────────────────────────────

ACCOUNTS_DATA = [
    ("physics",      "user01", "200", 0.31, 48502198, 0.0812, "0.42"),
    ("physics",      "user02", "200", 0.28, 52301440, 0.0877, "0.38"),
    ("physics",      "user03", "200", 0.35, 41200100, 0.0691, "0.48"),
    ("physics",      "user04", "200", 0.22, 61003200, 0.1023, "0.29"),
    ("cs",           "user13", "180", 0.18, 71200800, 0.1194, "0.21"),
    ("cs",           "user14", "180", 0.24, 58100300, 0.0975, "0.31"),
    ("cs",           "user15", "180", 0.20, 65400100, 0.1097, "0.25"),
    ("cs",           "user16", "180", 0.27, 53200800, 0.0893, "0.35"),
    ("cs",           "user17", "180", 0.15, 78100200, 0.1310, "0.18"),
    ("genomics",     "user29", "160", 0.19, 69300100, 0.1162, "0.22"),
    ("genomics",     "user30", "160", 0.25, 55100800, 0.0924, "0.33"),
    ("chemistry",    "user05", "150", 0.52, 29100200, 0.0488, "0.71"),
    ("chemistry",    "user06", "150", 0.48, 32400100, 0.0543, "0.65"),
    ("biology",      "user09", "150", 0.55, 27200300, 0.0456, "0.74"),
    ("biology",      "user10", "150", 0.61, 22100100, 0.0371, "0.82"),
    ("engineering",  "user18", "120", 0.58, 25300200, 0.0424, "0.78"),
    ("neuroscience", "user36", "110", 0.63, 20100300, 0.0337, "0.85"),
    ("materials",    "user25", "100", 0.66, 18200100, 0.0305, "0.89"),
    ("climate",      "user45", "130", 0.54, 28300400, 0.0475, "0.73"),
    ("energy",       "user48", "100", 0.72, 14100200, 0.0237, "0.94"),
    ("astronomy",    "user33", "90",  0.78, 10200300, 0.0171, "1.02"),
    ("math",         "user22", "80",  0.85, 6100200,  0.0102, "1.18"),
    ("math",         "user23", "80",  0.81, 8200100,  0.0138, "1.10"),
    ("economics",    "user40", "60",  0.88, 4100300,  0.0069, "1.25"),
    ("linguistics",  "user43", "40",  0.95, 1200100,  0.0020, "1.42"),
    ("linguistics",  "user44", "40",  0.97, 800200,   0.0013, "1.51"),
    ("admin",        "user50", "50",  0.92, 2100100,  0.0035, "1.35"),
]

QUEUE_DATA = [
    # Running jobs
    ("84501", "sim_physics",  "user01", "physics",   "RUNNING", 12450, "None"),
    ("84502", "sim_physics",  "user02", "physics",   "RUNNING", 12200, "None"),
    ("84510", "sim_cs",       "user13", "cs",        "RUNNING", 11800, "None"),
    ("84515", "sim_cs",       "user17", "cs",        "RUNNING", 11500, "None"),
    ("84520", "sim_genomics", "user29", "genomics",  "RUNNING", 11900, "None"),
    ("84530", "sim_chem",     "user05", "chemistry", "RUNNING", 13100, "None"),
    ("84535", "sim_bio",      "user10", "biology",   "RUNNING", 13800, "None"),
    ("84540", "sim_eng",      "user18", "engineering","RUNNING", 13500, "None"),
    # Pending jobs (sorted by priority — high fairshare users first!)
    ("84600", "sim_ling",     "user44", "linguistics","PENDING", 15200, "Resources"),
    ("84601", "sim_ling",     "user43", "linguistics","PENDING", 15050, "Resources"),
    ("84605", "sim_admin",    "user50", "admin",     "PENDING", 14800, "Resources"),
    ("84610", "sim_econ",     "user40", "economics", "PENDING", 14500, "Resources"),
    ("84615", "sim_math",     "user22", "math",      "PENDING", 14200, "Resources"),
    ("84620", "sim_math",     "user23", "math",      "PENDING", 14100, "Resources"),
    ("84625", "sim_astro",    "user33", "astronomy", "PENDING", 13900, "Resources"),
    ("84630", "sim_energy",   "user48", "energy",    "PENDING", 13700, "Resources"),
    ("84640", "sim_neuro",    "user36", "neuroscience","PENDING",13400, "Resources"),
    ("84650", "sim_mat",      "user25", "materials", "PENDING", 13200, "Resources"),
    ("84660", "sim_climate",  "user45", "climate",   "PENDING", 13000, "Resources"),
    ("84670", "sim_bio",      "user09", "biology",   "PENDING", 12800, "Resources"),
    ("84680", "sim_chem",     "user06", "chemistry", "PENDING", 12600, "Resources"),
    ("84700", "sim_physics",  "user03", "physics",   "PENDING", 11100, "Priority"),
    ("84710", "sim_cs",       "user14", "cs",        "PENDING", 10800, "Priority"),
    ("84720", "sim_genomics", "user30", "genomics",  "PENDING", 10500, "Priority"),
    ("84730", "sim_cs",       "user15", "cs",        "PENDING", 10200, "Priority"),
    ("84740", "sim_physics",  "user04", "physics",   "PENDING",  9800, "Priority"),
    ("84750", "sim_cs",       "user17", "cs",        "PENDING",  9500, "Priority"),
]

FACTORS_DATA = [
    # job_id, user, priority, age, fairshare, jobsize, partition, qos
    ("84600", "user44", 15200, 180, 9500, 500, 1000, 4020),
    ("84601", "user43", 15050, 170, 9400, 500, 1000, 3980),
    ("84605", "user50", 14800, 160, 9200, 500, 1000, 3940),
    ("84610", "user40", 14500, 150, 8800, 500, 1000, 4050),
    ("84615", "user22", 14200, 200, 8500, 500, 1000, 4000),
    ("84620", "user23", 14100, 190, 8400, 500, 1000, 4010),
    ("84625", "user33", 13900, 140, 8200, 500, 1000, 4060),
    ("84630", "user48", 13700, 130, 7200, 500, 1000, 4870),
    ("84640", "user36", 13400, 120, 6300, 500, 1000, 5480),
    ("84650", "user25", 13200, 110, 6600, 500, 1000, 4990),
    ("84700", "user03", 11100, 100, 3500, 500, 1000, 6000),
    ("84710", "user14", 10800, 90,  2400, 500, 1000, 6810),
    ("84730", "user15", 10200, 80,  2000, 500, 1000, 6620),
    ("84740", "user04", 9800,  70,  2200, 500, 1000, 6030),
    ("84750", "user17", 9500,  60,  1500, 500, 1000, 6440),
]


def bar(value, max_val, width=15):
    if max_val <= 0:
        return "░" * width
    ratio = min(value / max_val, 1.0)
    filled = int(width * ratio)
    return "█" * filled + "░" * (width - filled)


def fs_style(fs):
    if fs >= 0.8: return "bold green"
    if fs >= 0.5: return "green"
    if fs >= 0.3: return "yellow"
    if fs >= 0.1: return "rgb(255,165,0)"
    return "red"


def state_style(s):
    if s == "RUNNING": return "green"
    if s == "PENDING": return "yellow"
    return "dim"


# ── Scene 1: Simulate Setup ────────────────────────────────────────

def scene_setup():
    console.print("\n[bold blue]━━━ Slurm Priority Dashboard Demo ━━━[/bold blue]\n")
    pause(1)

    type_cmd("playground simulate setup")

    console.print("[bold blue]━━━ Priority Simulation Setup ━━━[/bold blue]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Users", "50")
    table.add_row("Accounts", "15")
    table.add_row("QOS tiers", "4")
    table.add_row("Est. jobs", "~30,000")
    table.add_row("Compute nodes", "5")
    table.add_row("CPUs/node", "1,000")
    table.add_row("Total job slots", "5,000")
    console.print(table)
    console.print()

    phases = [
        ("Phase 1: Create Unix users", "Created 50 users across 6 containers"),
        ("Phase 2: Configure accounting", "Created 15 accounts, 50 users, 4 QOS tiers"),
        ("Phase 3: Scale nodes", "5 nodes × 1,000 CPUs = 5,000 total job slots"),
        ("Phase 4: Submit jobs", "Submitted 29,847 / 29,847 target jobs"),
    ]

    for name, result in phases:
        console.print(f"  [green]✓[/green] {name}: {result}")
        pause(0.5)

    console.print()
    console.print("[bold blue]━━━ Setup Complete ━━━[/bold blue]\n")
    pause(1)


# ── Scene 2: Full TUI Dashboard ────────────────────────────────────

def scene_dashboard():
    type_cmd("playground priority live -u user01")

    sections = []

    # Fairshare section
    sections.append(Text.assemble(
        ("Fairshare by Account / User", "bold cyan"),
        ("  14:32:18\n", "dim"),
    ))

    fs_table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1), expand=True)
    fs_table.add_column("Account", min_width=12)
    fs_table.add_column("User", min_width=8)
    fs_table.add_column("Shares", justify="right")
    fs_table.add_column("FairShare", justify="right")
    fs_table.add_column("", min_width=15)
    fs_table.add_column("RawUsage", justify="right")
    fs_table.add_column("EffUsage", justify="right")
    fs_table.add_column("LevelFS", justify="right")

    for acct, user, shares, fs, usage, eff, lfs in ACCOUNTS_DATA[:20]:
        style = fs_style(fs)
        row_style = "bold reverse" if user == "user01" else ""
        fs_table.add_row(
            acct, user, shares,
            f"[{style}]{fs:.4f}[/{style}]",
            f"[{style}]{bar(fs, 1.0)}[/{style}]",
            f"{usage:,}", f"{eff:.4f}", lfs,
            style=row_style,
        )

    sections.append(fs_table)
    sections.append(Text(""))

    # Queue section
    sections.append(Text("Job Queue  (sorted by priority)\n", style="bold cyan"))

    q_table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1), expand=True)
    q_table.add_column("#", justify="right", min_width=3)
    q_table.add_column("JobID", min_width=6)
    q_table.add_column("Name", min_width=12, max_width=16)
    q_table.add_column("User", min_width=8)
    q_table.add_column("Account", min_width=10)
    q_table.add_column("State", min_width=7)
    q_table.add_column("Priority", justify="right")
    q_table.add_column("Reason", min_width=10)

    pending_rank = 0
    for jid, name, user, acct, state, prio, reason in QUEUE_DATA:
        is_pending = state == "PENDING"
        if is_pending:
            pending_rank += 1
            rank = str(pending_rank)
        else:
            rank = "-"
        ss = state_style(state)
        row_style = "bold reverse" if user == "user01" else ""
        q_table.add_row(
            rank, jid, name, user, acct,
            f"[{ss}]{state}[/{ss}]",
            f"{prio:,}", reason if reason != "None" else "",
            style=row_style,
        )

    sections.append(q_table)
    sections.append(Text.assemble(
        ("\n  Running: ", "dim"), ("5,024", "green"),
        ("  Pending: ", "dim"), ("24,976", "yellow"),
        ("  Total: ", "dim"), ("30,000", ""),
    ))
    sections.append(Text(""))

    # Priority factors section
    sections.append(Text("Priority Factor Breakdown  (pending jobs)\n", style="bold cyan"))

    p_table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1), expand=True)
    p_table.add_column("JobID", min_width=6)
    p_table.add_column("User", min_width=8)
    p_table.add_column("Priority", justify="right")
    p_table.add_column("", min_width=15)
    p_table.add_column("Age", justify="right")
    p_table.add_column("FairShr", justify="right")
    p_table.add_column("JobSize", justify="right")
    p_table.add_column("Part", justify="right")
    p_table.add_column("QOS", justify="right")
    p_table.add_column("Biggest Factor")

    max_prio = max(f[2] for f in FACTORS_DATA)
    for jid, user, prio, age, fs, js, part, qos in FACTORS_DATA[:12]:
        factors = {"Age": age, "FairShare": fs, "JobSize": js, "Partition": part, "QOS": qos}
        biggest = max(factors, key=factors.get)
        pct = f"{factors[biggest] / prio * 100:.0f}%" if prio > 0 else "-"
        p_table.add_row(
            jid, user, f"{prio:,}", bar(prio, max_prio),
            str(age), str(fs), str(js), str(part), str(qos),
            f"{biggest} ({pct})",
        )

    sections.append(p_table)
    sections.append(Text(""))

    # Config section
    sections.append(Text("Priority Weights (active config)\n", style="bold cyan"))
    sections.append(Text(
        "  Age: 1000  Fairshare: 10000  JobSize: 500  Partition: 1000  QOS: 2000  "
        "Decay½Life: 7-0  MaxAge: 7-0\n",
        style="dim",
    ))

    panel = Panel(
        Group(*sections),
        title="[bold] Slurm Priority Dashboard [/bold]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)
    pause(3)


# ── Scene 3: Watch mode ────────────────────────────────────────────

def scene_watch():
    console.print()
    type_cmd("playground priority watch -u user01")

    lines = [
        "R:5.0k P:25k | user01 fs:0.31 #14/25k (r:842 p:358) | hi:user44(0.97) lo:user17(0.15)",
        "R:5.0k P:25k | user01 fs:0.31 #14/25k (r:843 p:357) | hi:user44(0.97) lo:user17(0.15)",
        "R:5.0k P:25k | user01 fs:0.31 #13/25k (r:845 p:355) | hi:user44(0.97) lo:user17(0.15)",
    ]

    for i, line in enumerate(lines):
        # Overwrite same line using ANSI cursor control
        if i > 0:
            sys.stdout.write("\033[A\033[2K")  # move up, clear line
            sys.stdout.flush()
        console.print(line)
        pause(1.5)

    console.print("[dim]^C[/dim]")
    pause(0.5)


# ── Scene 4: tmux status ───────────────────────────────────────────

def scene_tmux():
    console.print()
    type_cmd("playground priority tmux-status -u user01")
    console.print("R:5.0k P:25k fs:0.31 #14")
    pause(1)

    type_cmd("playground priority tmux-status -u user44 --color")
    console.print("#[fg=green]R:5.0k#[default] P:25k #[fg=green]fs:0.97#[default] #1")
    pause(1)

    # Show what it looks like in tmux
    console.print()
    console.print("[dim]# In a tmux status bar, it renders as:[/dim]")
    pause(0.3)
    console.print(
        "┌────────────────────────────────────────────────────"
        "─────────────────────────────────────────────────────────┐"
    )
    console.print(
        "│ [bold]0:vim[/bold]  1:bash  2:logs"
        "                                           "
        "[green]R:5.0k[/green] P:25k [yellow]fs:0.31 #14[/yellow] │"
    )
    console.print(
        "└────────────────────────────────────────────────────"
        "─────────────────────────────────────────────────────────┘"
    )
    pause(2)


# ── Scene 5: Explain ───────────────────────────────────────────────

def scene_explain():
    console.print()
    type_cmd("playground priority explain 84600")

    console.print("\n[bold blue]=== Priority Explanation: Job 84600 ===[/bold blue]\n")
    console.print("[bold]Job:[/bold]       84600")
    console.print("[bold]User:[/bold]      user44")
    console.print("[bold]Priority:[/bold]  15,200")
    console.print()

    console.print("[bold]Factor Contributions:[/bold]")
    console.print(f"  {'Factor':<12} {'Score':>8}  {'Weight':>8}  {'% of Total':>10}  Bar")
    console.print(f"  {'─' * 12} {'─' * 8}  {'─' * 8}  {'─' * 10}  {'─' * 20}")

    factors = [
        ("Age",       180,  "1000",  1.2,  "dim"),
        ("FairShare", 9500, "10000", 62.5, "bold green"),
        ("JobSize",   500,  "500",   3.3,  "dim"),
        ("Partition", 1000, "1000",  6.6,  "dim"),
        ("QOS",       4020, "2000",  26.4, "yellow"),
    ]
    max_f = 9500
    for name, score, weight, pct, style in factors:
        b = bar(score, max_f, width=20)
        console.print(f"  [{style}]{name:<12} {score:>8}  {weight:>8}  {pct:>9.1f}%  {b}[/{style}]")

    console.print()
    console.print("[bold]Queue Position:[/bold] 1 of 24,976 pending jobs")
    console.print("  → [green]This job is next to run[/green]")
    console.print()

    console.print("[bold]User FairShare Context:[/bold]")
    console.print("  Account:     linguistics")
    console.print(f"  FairShare:   [bold green]0.9700[/bold green]  {bar(0.97, 1.0)}")
    console.print("  Raw Usage:   800,200")
    console.print("  Eff Usage:   0.0013")
    console.print("  Level FS:    1.51")
    console.print("  → [green]High fairshare — this user is under-utilizing their allocation[/green]")
    console.print()
    pause(2)


# ── Scene 6: Teardown ──────────────────────────────────────────────

def scene_teardown():
    type_cmd("playground simulate teardown")

    console.print("[bold blue]━━━ Priority Simulation Teardown ━━━[/bold blue]\n")
    console.print("  [green]✓[/green] Teardown complete: Simulation fully cleaned up, cluster restored to default 2-node config")
    console.print()
    pause(1)


# ── Main ────────────────────────────────────────────────────────────

def main():
    scene_setup()
    scene_dashboard()
    scene_watch()
    scene_tmux()
    scene_explain()
    scene_teardown()

    console.print("[bold blue]━━━ Demo Complete ━━━[/bold blue]\n")
    console.print("[dim]All features: TUI dashboard, watch mode, tmux status, vim statusline, job explain[/dim]")
    console.print("[dim]Docs: playground/docs/priority-simulation.md | playground/tmux/README.md[/dim]")
    console.print()
    pause(2)


if __name__ == "__main__":
    main()
