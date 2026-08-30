# Token growth vs auto-compaction (model only - see Risks R-2)
# Sawtooth: growth 1500 tok/turn from ~800 system prompt, compact at threshold
# to ~3700 (summary + 2 protected rounds). Threshold = 128000 * 95% = 121600.
set terminal pngcairo size 900,430 enhanced font "DejaVu Sans,10"
set output "img/token-growth.png"
set title "Modeled prompt size over rounds (CONTEXT_SIZE=128000, pct=95%)"
set xlabel "Conversation rounds"
set ylabel "Prompt tokens"
set grid
set datafile missing "nan"
set key left top

threshold(x) = 121600
y(x) = x <= 80 ? (800 + 1500*x) : (3700 + 1500*(x-80))

set style line 1 lc rgb "#2b6f9e" lw 2
set style line 2 lc rgb "#b07c2a" lw 1.5 lt 2

plot y(x) with lines ls 1 title "prompt size (model)", \
     threshold(x) with lines ls 2 title "compact threshold 121.6k"