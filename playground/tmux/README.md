# Slurm tmux & Vim Integration

Always-visible Slurm job status in your tmux status bar and Vim statusline — no context switching needed.

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ tmux status bar                    R:5k P:25k fs:0.82 #3  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  vim / your editor                                          │
│                                                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ vim statusline                     R:5k P:25k fs:0.82 #3  │
└─────────────────────────────────────────────────────────────┘
```

`slurm-status.sh` calls `playground priority tmux-status` and caches the result for 10 seconds. tmux reads it periodically. Vim reads the same cache file — zero extra subprocess calls.

## tmux Setup

Add to your `~/.tmux.conf`:

```bash
# Basic (no user personalization)
set -g status-right '#(/path/to/playground/tmux/slurm-status.sh)'
set -g status-interval 10

# With user personalization (shows your fairshare and queue rank)
set -g status-right '#(/path/to/playground/tmux/slurm-status.sh -u yourname)'
set -g status-interval 10

# With tmux colors
set -g status-right '#(/path/to/playground/tmux/slurm-status.sh -u yourname --color)'
set -g status-interval 10
```

Then reload: `tmux source-file ~/.tmux.conf`

### What You'll See

Without `-u`:
```
R:5k P:25k
```

With `-u user01`:
```
R:5k P:25k fs:0.82 #3
```
- `R:5k` — 5,000 running jobs
- `P:25k` — 25,000 pending jobs
- `fs:0.82` — your fairshare score (higher = more priority)
- `#3` — your best pending job is #3 in the queue

### Cache Tuning

The script caches results to avoid hammering the cluster. Adjust the TTL:

```bash
# Cache for 30 seconds instead of default 10
export SLURM_TMUX_CACHE_TTL=30
```

## Vim / Neovim Setup

### Prerequisites

The Vim plugin reads the tmux cache file, so make sure `slurm-status.sh` is running via tmux first (see above).

### Vim 8+

```vim
" Source the plugin
source /path/to/playground/vim/slurm.vim

" Add to your statusline
set statusline+=%{SlurmStatus()}
```

### With vim-airline

```vim
source /path/to/playground/vim/slurm.vim
let g:airline_section_y = '%{SlurmStatus()}'
```

### With Neovim + lualine

```lua
require('lualine').setup {
  sections = {
    lualine_y = {
      function() return vim.fn.SlurmStatus() end
    }
  }
}
```

The plugin auto-refreshes every 10 seconds by triggering `redrawstatus`. It's reading a local cache file, so there's no performance impact.

## CLI Alternatives

If you prefer a dedicated terminal pane over the status bar:

```bash
# One-liner that refreshes every 5 seconds (great for a small tmux split)
playground priority watch -u yourname

# Same but with account-level view
playground priority watch -a physics

# Print once and exit (for scripting)
playground priority watch --no-loop

# JSON output for piping
playground priority watch --no-loop --format json
```

## All Output Modes

| Mode | Command | Use Case |
|------|---------|----------|
| **Full TUI** | `playground priority live` | Dedicated monitoring terminal |
| **Watch line** | `playground priority watch` | Small tmux pane |
| **tmux status** | via `slurm-status.sh` | Always visible, zero effort |
| **Vim statusline** | via `slurm.vim` | See status without leaving editor |
| **One-shot** | `playground priority show` | Quick check |
| **JSON** | `playground priority watch --no-loop --format json` | Scripts/automation |
