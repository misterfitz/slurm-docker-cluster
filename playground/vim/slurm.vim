" slurm.vim — Vim/Neovim statusline integration for Slurm priority info.
"
" Reads from the tmux cache file (populated by slurm-status.sh) so it's
" essentially free — no subprocess calls from Vim.
"
" Setup:
"   1. Make sure slurm-status.sh is running via tmux (see tmux/README.md)
"   2. Source this file:  source /path/to/playground/vim/slurm.vim
"   3. Add to your statusline:
"        set statusline+=%{SlurmStatus()}
"
"      Or with vim-airline:
"        let g:airline_section_y = '%{SlurmStatus()}'
"
"      Or with lualine (Neovim):
"        lualine_y = { function() return vim.fn.SlurmStatus() end }

function! SlurmStatus() abort
    let l:cache = '/tmp/slurm-tmux-status-' . $USER . '.cache'
    if filereadable(l:cache)
        let l:lines = readfile(l:cache)
        if len(l:lines) > 0
            " Strip tmux color codes if present (#[...])
            let l:line = substitute(l:lines[0], '#\[[^\]]*\]', '', 'g')
            return l:line
        endif
    endif
    return ''
endfunction

" Optional: auto-refresh the statusline every 10 seconds.
" The cache file is updated by slurm-status.sh (via tmux), so this
" just triggers a redraw to pick up the latest cached value.
if has('timers')
    function! s:RefreshSlurmStatus(timer) abort
        redrawstatus
    endfunction

    " Refresh every 10 seconds (10000ms). Adjust as needed.
    let s:slurm_timer = timer_start(10000, function('s:RefreshSlurmStatus'), {'repeat': -1})
endif
