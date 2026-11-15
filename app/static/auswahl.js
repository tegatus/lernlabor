// Tabs, "alle"-Knöpfe und Live-Trefferzahl für das Auswahl-Widget
document.querySelectorAll('.auswahl').forEach(box => {
  box.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
    box.querySelectorAll('.tab, .tabpanel').forEach(e => e.classList.remove('aktiv'));
    tab.classList.add('aktiv');
    box.querySelector('#' + tab.dataset.tab).classList.add('aktiv');
  }));
  box.querySelectorAll('button.alle').forEach(b => b.addEventListener('click', ev => {
    ev.preventDefault();
    const boxes = [...document.getElementById(b.dataset.scope).querySelectorAll('input[type=checkbox]')];
    const alleAn = boxes.every(c => c.checked);
    boxes.forEach(c => { c.checked = !alleAn; });
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }));
});

const ziel = document.querySelector('[data-trefferzahl]');
if (ziel) {
  const form = ziel.closest('form');
  let timer;
  const update = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const p = new URLSearchParams();
      for (const [k, v] of new FormData(form)) if (['thema', 'lernziel', 'bivo', 'k'].includes(k)) p.append(k, v);
      if (ziel.dataset.pruefung) p.append('pruefung', '1');
      const r = await fetch(ziel.dataset.trefferzahl + '?' + p);
      const n = (await r.json()).anzahl;
      ziel.textContent = n === 0 ? 'Keine passenden Aufgaben' : `${n} passende Aufgabe${n === 1 ? '' : 'n'} in der Datenbank`;
    }, 200);
  };
  form.addEventListener('change', update);
  update();
}
