"""Render the public benchmark figure from the checked measurement summary."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
s = json.loads((ROOT / 'benchmarks/pro6000-2026-10-12/summary.json').read_text())
OUT = ROOT / 'docs/assets'
OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.spines.left': False,
                     'axes.edgecolor': '#d5ddd7', 'axes.facecolor': '#f5f8f4',
                     'figure.facecolor': '#ffffff', 'text.color': '#173629',
                     'axes.labelcolor': '#42614f', 'xtick.color': '#42614f', 'ytick.color': '#42614f'})
fig, axes = plt.subplots(1, 4, figsize=(15.5, 4.2))
cases = [
    ('Return to 32K chat', 'seconds to first token', s['main_conversation_resume_ttft_seconds'], '38.3× faster resume', False),
    ('Fresh 32K input', 'seconds to first token', s['full_profile_mixed_sequence_ttft_seconds']['32768'], '10.5% less waiting', False),
    ('Fresh 4K after large chats', 'seconds to first token', s['full_profile_mixed_sequence_ttft_seconds']['4096'], 'First parking costs time', True),
    ('Code generation', 'tokens / second', {'baseline': s['decode_tokens_per_second']['code']['baseline'], 'optimized': s['decode_tokens_per_second']['code']['optimized']}, 'Essentially unchanged', False),
]
for ax, (title, units, row, note, cost) in zip(axes, cases):
    values = [row['baseline'], row['optimized']]
    bars = ax.bar(['Strata baseline', 'Sprint'], values, color=['#8b9b91', '#c57848' if cost else '#25815b'], width=.58)
    ax.bar_label(bars, labels=[f'{v:.3f}' if v < 1 else f'{v:.2f}' if v < 30 else f'{v:.1f}' for v in values], padding=5, fontsize=12)
    ax.set_ylim(0, max(values) * 1.28); ax.set_title(title, fontsize=12, pad=26)
    ax.set_ylabel(units, fontsize=9); ax.grid(axis='y', alpha=.12); ax.set_axisbelow(True)
    ax.tick_params(axis='both', length=0); ax.text(.5, -.21, note, transform=ax.transAxes, ha='center', fontsize=10,
                                                           color='#945b35' if cost else '#285c3d')
fig.suptitle('FULL PROFILE  /  Same GPU · Same model · Same precision', fontsize=15, x=.035, ha='left', y=1.03)
fig.tight_layout(w_pad=2.3)
fig.text(.035, -.06, 'GPU-host loopback TTFT includes parking. Means: 12 conversation returns; 3 trials for other panels. Strata 0.1.43, PRO 6000, IQ3_S, FP16 KV.', fontsize=9, color='#64746b')
fig.savefig(OUT / 'benchmark.svg', bbox_inches='tight')
svg = OUT / 'benchmark.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
fig.savefig(OUT / 'benchmark.png', dpi=160, bbox_inches='tight')
plt.close(fig)
(OUT / 'metrics.json').write_text(json.dumps(s, ensure_ascii=False, indent=2) + '\n')
print('Rendered benchmark.svg, benchmark.png and metrics.json from recorded evidence.')
