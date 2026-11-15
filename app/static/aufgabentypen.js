// Editor-Bereich für Aufgabentypen: Variablen & Formeln, MC-Optionen, Zuordnungspaare, Lückentext-Optionen.
// Die Daten werden als JSON im versteckten Feld "daten" gespeichert.
(() => {
  const form = document.getElementById('aufgabe-form');
  const panel = document.getElementById('typ-panel');
  const ablage = document.getElementById('typ-daten');
  if (!form || !panel) return;
  const VORSCHLAG = { rechnung: 'karo', mc: 'keins', zuordnung: 'keins', luecken: 'keins' };
  let daten = {};
  try { daten = JSON.parse(ablage.value || '{}') || {}; } catch (e) { daten = {}; }
  let seed = 1;
  const typ = () => form.querySelector('input[name=typ]:checked')?.value || 'frei';
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  window.aufgabeTypDaten = () => ({ typ: typ(), daten, seed });
  function speichern() {
    ablage.value = JSON.stringify(daten);
    window.vorschauAktualisieren && window.vorschauAktualisieren();
  }

  // ---------------------------------------------------------- Tabellen-Baustein
  // spalten: [{key, label, typ: 'text'|'zahl'|'check', breite, platzhalter}]
  function tabelle(titel, liste, spalten, neu, hinweis = '', nachAenderung = null) {
    const geaendert = () => { nachAenderung && nachAenderung(); speichern(); };
    const box = document.createElement('div');
    box.className = 'typ-tabelle';
    const zeichnen = () => {
      box.innerHTML = `<div class="typ-kopf"><strong>${titel}</strong>${hinweis ? `<span class="muted">${hinweis}</span>` : ''}</div>
        <table class="tab kompakt"><tr>${spalten.map(s => `<th style="width:${s.breite || 'auto'}">${s.label}</th>`).join('')}<th style="width:2rem"></th></tr>
        ${liste.map((z, i) => `<tr data-i="${i}">${spalten.map(s => s.typ === 'check'
          ? `<td style="text-align:center"><input type="checkbox" data-k="${s.key}" ${z[s.key] ? 'checked' : ''}></td>`
          : `<td><input data-k="${s.key}" ${s.typ === 'zahl' ? 'inputmode="decimal"' : ''} value="${esc(z[s.key])}" placeholder="${s.platzhalter || ''}"></td>`).join('')}
          <td><button type="button" class="link weg" title="Zeile löschen">✕</button></td></tr>`).join('')}
        </table><button type="button" class="btn klein sek dazu">+ Zeile</button>`;
    };
    box.addEventListener('input', e => {
      const tr = e.target.closest('tr[data-i]'); if (!tr) return;
      const s = spalten.find(x => x.key === e.target.dataset.k);
      let v = s.typ === 'check' ? e.target.checked : e.target.value;
      if (s.typ === 'zahl') v = v.replace(',', '.');
      liste[+tr.dataset.i][s.key] = v;
      geaendert();
    });
    box.addEventListener('click', e => {
      if (e.target.closest('.dazu')) { liste.push(neu()); zeichnen(); geaendert(); box.querySelector('tr:last-child input')?.focus(); }
      const weg = e.target.closest('.weg');
      if (weg) { liste.splice(+weg.closest('tr').dataset.i, 1); zeichnen(); geaendert(); }
    });
    zeichnen();
    return box;
  }
  function schalter(key, text, standard) {
    const l = document.createElement('label');
    l.innerHTML = `<input type="checkbox" ${(daten[key] ?? standard) ? 'checked' : ''}> ${text}`;
    l.querySelector('input').addEventListener('change', e => { daten[key] = e.target.checked; speichern(); });
    if (daten[key] === undefined) daten[key] = standard;
    return l;
  }
  function absatz(html) { const p = document.createElement('p'); p.className = 'muted'; p.innerHTML = html; return p; }

  // ---------------------------------------------------------- Panels je Typ
  const PANELS = {
    rechnung() {
      daten.variablen ||= [{ name: 'n', min: 40, max: 70, schritt: 1 }];
      daten.ergebnisse ||= [{ name: 'c', formel: 'n * 2 * 10^4', stellen: 3 }];
      return [
        absatz('Schreibe im Aufgabentext und in der Lösung <code>{name}</code> – z. B. «Du zählst <code>{n}</code> Zellen» und ' +
               '«c = <code>{n}</code> × 2 × 10^{4} = <code>{c}</code> Zellen/mL». Jedes Übungsblatt erhält eigene Zahlen; ' +
               'das Lösungsblatt rechnet mit denselben Werten.'),
        tabelle('Variablen (Zufallswerte)', daten.variablen, [
          { key: 'name', label: 'Name', breite: '18%', platzhalter: 'n' },
          { key: 'min', label: 'von', typ: 'zahl', breite: '18%' },
          { key: 'max', label: 'bis', typ: 'zahl', breite: '18%' },
          { key: 'schritt', label: 'Schritt', typ: 'zahl', breite: '18%', platzhalter: '1 oder 0,1' },
        ], () => ({ name: '', min: 1, max: 10, schritt: 1 })),
        tabelle('Ergebnisse (berechnet)', daten.ergebnisse, [
          { key: 'name', label: 'Name', breite: '18%', platzhalter: 'c' },
          { key: 'formel', label: 'Formel', platzhalter: 'n * 2 * 10^4' },
          { key: 'stellen', label: 'gültige Ziffern', typ: 'zahl', breite: '16%' },
        ], () => ({ name: '', formel: '', stellen: 3 }),
          'erlaubt: + − * / ^, Klammern, sqrt, log10, ln, exp, round, pi'),
        (() => {
          const b = document.createElement('button'); b.type = 'button'; b.className = 'btn klein sek';
          b.textContent = '🎲 Andere Beispielzahlen in der Vorschau';
          b.addEventListener('click', () => { seed = Math.floor(Math.random() * 1e9); speichern(); });
          return b;
        })(),
      ];
    },
    mc() {
      daten.optionen ||= [{ text: '', korrekt: true }, { text: '', korrekt: false }, { text: '', korrekt: false }];
      return [
        absatz('Der Aufgabentext ist die Frage. Antwortoptionen hier erfassen und die richtigen ankreuzen; ' +
               'die Musterlösung kann eine Begründung enthalten.'),
        tabelle('Antwortoptionen', daten.optionen, [
          { key: 'korrekt', label: 'richtig', typ: 'check', breite: '4.5rem' },
          { key: 'text', label: 'Antwort' },
        ], () => ({ text: '', korrekt: false })),
        schalter('mischen', 'Reihenfolge pro Blatt mischen', true),
      ];
    },
    zuordnung() {
      daten.paare ||= [['', ''], ['', ''], ['', '']];
      const zeilen = daten.paare.map(([l, r]) => ({ l, r }));
      const sync = () => { daten.paare = zeilen.map(z => [z.l ?? '', z.r ?? '']); };
      const t = tabelle('Paare', zeilen, [
        { key: 'l', label: 'Begriff', breite: '35%' }, { key: 'r', label: 'passende Beschreibung' },
      ], () => ({ l: '', r: '' }), '', sync);
      return [absatz('Die Beschreibungen werden auf jedem Blatt gemischt und mit Buchstaben versehen.'), t,
              schalter('mischen', 'Beschreibungen mischen', true)];
    },
    luecken() {
      return [
        absatz('Markiere im Aufgabentext jede Lücke mit doppelten geschweiften Klammern: ' +
               '<code>Die PCR beginnt mit der {{Denaturierung}} bei {{95 °C|94 °C}}.</code> ' +
               'Nach <code>|</code> stehen weitere akzeptierte Antworten (nur in der Lösung).'),
        schalter('wortliste', 'Wortliste unter dem Text anzeigen (gemischt)', false),
      ];
    },
  };

  let letzterTyp = typ();
  function zeigen() {
    const t = typ();
    panel.innerHTML = '';
    panel.hidden = !PANELS[t];
    if (PANELS[t]) PANELS[t]().forEach(el => panel.appendChild(el));
    speichern();
  }
  form.querySelectorAll('input[name=typ]').forEach(r => r.addEventListener('change', () => {
    const t = typ();
    if (t !== letzterTyp && VORSCHLAG[t]) form.querySelector('select[name=antwortformat]').value = VORSCHLAG[t];
    letzterTyp = t;
    zeigen();
  }));
  // Für den KI-Assistenten: Typ und Daten von aussen setzen
  window.aufgabeTypSetzen = (t, d) => {
    const r = form.querySelector(`input[name=typ][value="${t}"]`) || form.querySelector('input[name=typ][value=frei]');
    r.checked = true; letzterTyp = r.value;
    daten = (d && typeof d === 'object') ? d : {};
    zeigen();
  };
  zeigen();
})();
