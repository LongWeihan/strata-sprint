let measurements;
const element = id => document.getElementById(id);
function render(mode) {
  if (!measurements) return;
  const full = mode === 'full';
  const rows = full ? [
    ['Return to 32K chat', measurements.main_conversation_resume_ttft_seconds],
    ['Fresh 32K input', measurements.full_profile_mixed_sequence_ttft_seconds['32768']],
    ['Fresh 4K after large chats', measurements.full_profile_mixed_sequence_ttft_seconds['4096']],
  ] : Object.entries(measurements.isolated_prefill_ttft_seconds).map(([tier, row]) => [`Fresh ${{4096: '4K', 32768: '32K', 122880: '123K'}[tier]} input`, row]);
  const max = Math.max(...rows.flatMap(([, row]) => [row.baseline, row.optimized]));
  const container = element('bars'); container.replaceChildren();
  rows.forEach(([label, row]) => {
    const group = document.createElement('div'); group.className = 'bar-group';
    const caption = document.createElement('div'); caption.className = 'bar-caption';
    const text = document.createElement('span'); text.textContent = label;
    const change = document.createElement('span'); const gain = 100 * (1 - row.optimized / row.baseline);
    change.className = gain >= 0 ? 'gain' : 'cost';
    change.textContent = `${Math.abs(gain).toFixed(1)}% ${gain >= 0 ? 'less' : 'more'} wait`;
    caption.append(text, change); group.append(caption);
    [['baseline', row.baseline], ['sprint', row.optimized]].forEach(([kind, value]) => {
      const track = document.createElement('div'); track.className = 'bar-track';
      const bar = document.createElement('div'); bar.className = `bar ${kind}`;
      bar.style.width = `${Math.max(1.2, value / max * 80)}%`;
      const number = document.createElement('span'); number.textContent = `${value.toFixed(3)} s`;
      track.setAttribute('aria-label', `${kind}: ${value.toFixed(3)} seconds`);
      track.append(bar, number); group.append(track);
    });
    container.append(group);
  });
  element('chart-title').textContent = full ? 'First-token wait · full profile' : 'First-token wait · isolated buffers';
  element('plot-note').textContent = full ? '12 returns; 3 trials for fresh-input rows. Full profile includes first-parking cost.' : 'Two repeats per tier. Only dedicated 8K buffers changed; conversation parking is disabled in this isolated comparison.';
  element('interpretation-title').textContent = full ? 'Less recomputation. More continuity.' : 'Dedicated space for new input.';
  element('interpretation').textContent = full ? 'Keeping the 32K main conversation parked avoids reading it again after a short side request.' : 'The buffer-only experiment isolates avoiding expert-cache borrowing. Do not read these gains as the full profile’s mixed-conversation latency.';
  document.querySelectorAll('[data-mode]').forEach(button => {
    const active = button.dataset.mode === mode;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
}
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => render(button.dataset.mode)));
fetch('assets/metrics.json').then(response => { if (!response.ok) throw new Error('metrics unavailable'); return response.json(); })
  .then(data => { measurements = data; render('full'); })
  .catch(() => { element('bars').textContent = 'The measurement file could not be loaded. The complete results remain in the table below and in the GitHub repository.'; });
