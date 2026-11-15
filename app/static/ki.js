// KI-Assistent im Aufgaben-Editor (nur geladen, wenn ein API-Schlüssel konfiguriert ist)
(() => {
  const panel = document.getElementById('ki-panel');
  const form = document.getElementById('aufgabe-form');
  if (!panel || !form) return;
  const ergebnis = document.getElementById('ki-ergebnis');
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const wert = sel => form.querySelector(sel)?.value ?? '';
  const gewaehlt = name => [...form.querySelectorAll(`input[name=${name}]:checked`)].map(x => x.value);

  panel.querySelectorAll('[data-ki]').forEach(t => t.addEventListener('click', () => {
    panel.querySelectorAll('[data-ki]').forEach(x => x.classList.toggle('aktiv', x === t));
    panel.querySelectorAll('[data-ki-teil]').forEach(x => { x.hidden = x.dataset.kiTeil !== t.dataset.ki; });
    ergebnis.hidden = true;
  }));

  function formular() {
    let daten = {};
    try { daten = JSON.parse(wert('#typ-daten') || '{}'); } catch (e) { /* leer lassen */ }
    return { titel: wert('[name=titel]'), text: wert('textarea[name=text]'), loesung: wert('textarea[name=loesung]'),
             typ: form.querySelector('input[name=typ]:checked')?.value || 'frei', daten,
             punkte: wert('[name=punkte]'), k_stufe: wert('[name=k_stufe]') };
  }
  function zeigen(html, art = '') { ergebnis.className = 'ki-ergebnis ' + art; ergebnis.innerHTML = html; ergebnis.hidden = false; }

  async function anfrage(aktion, nutzlast) {
    const knopf = panel.querySelector(`[data-ki-start=${aktion}]`);
    knopf.disabled = true;
    const alt = knopf.textContent; knopf.textContent = 'KI arbeitet … (bis ca. 1 Minute)';
    zeigen('<span class="lader"></span> Anfrage läuft …');
    try {
      const r = await fetch(panel.dataset.url.replace('/X', '/' + aktion), {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF }, body: JSON.stringify(nutzlast) });
      const d = await r.json().catch(() => ({ fehler: `Serverfehler (${r.status})` }));
      if (!r.ok || d.fehler) throw new Error(d.fehler || r.status);
      return d;
    } catch (e) {
      zeigen('⚠️ ' + esc(e.message), 'fehler');
      return null;
    } finally { knopf.disabled = false; knopf.textContent = alt; }
  }

  function aufgabeEinsetzen(a) {
    form.querySelector('[name=titel]').value = a.titel;
    form.querySelector('textarea[name=text]').value = a.text;
    form.querySelector('textarea[name=loesung]').value = a.loesung;
    form.querySelector('[name=punkte]').value = String(a.punkte).replace('.', ',');
    if (a.k_stufe) form.querySelector('[name=k_stufe]').value = String(a.k_stufe);
    window.aufgabeTypSetzen && window.aufgabeTypSetzen(a.typ, a.daten);
    form.querySelector('[name=antwortformat]').value = a.antwortformat;     // nach Typwahl (die setzt Vorschläge)
    form.querySelector('[name=antwortraum_cm]').value = String(a.antwortraum_cm).replace('.', ',');
    form.querySelector('textarea[name=text]').dispatchEvent(new Event('input', { bubbles: true }));
  }
  const hinweisListe = h => h && h.length ? `<ul class="ki-hinweise">${h.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';

  // ---------------------------------------------------------- Aktionen
  const BEREICHE = { aufgabe: 'Aufgabe', loesung: 'Lösung', punkte: 'Punkte', sprache: 'Sprache', fachlich: 'Fachlich' };
  const AKTIONEN = {
    async entwurf() {
      const f = formular();
      if ((f.text.trim() || f.loesung.trim()) && !confirm('Titel, Aufgabentext und Lösung durch den KI-Entwurf ersetzen?')) return;
      const d = await anfrage('entwurf', { lernziele: gewaehlt('lernziel'), bivo: gewaehlt('bivo'), themen: gewaehlt('thema'),
        typ: f.typ, k_stufe: f.k_stufe, punkte: f.punkte, wunsch: wert('#ki-wunsch') });
      if (!d) return;
      aufgabeEinsetzen(d.aufgabe);
      zeigen(`✅ Entwurf eingesetzt – bitte prüfen, anpassen und speichern.${d.aufgabe.kommentar ? `<p class="muted">KI-Notiz: ${esc(d.aufgabe.kommentar)}</p>` : ''}${hinweisListe(d.hinweise)}`, 'ok');
    },
    async pruefen() {
      const f = formular();
      if (!f.text.trim()) return zeigen('Zuerst einen Aufgabentext erfassen.', 'fehler');
      const d = await anfrage('pruefen', f);
      if (!d) return;
      const symbol = { in_ordnung: '✅', kleine_hinweise: '💡', fehler_gefunden: '⚠️' }[d.urteil] || '';
      zeigen(`<p><strong>${symbol} ${esc(d.zusammenfassung)}</strong></p>` + (d.befunde.length ? `<ul class="ki-befunde">${d.befunde.map(b =>
        `<li class="${b.schwere}"><span class="badge">${b.schwere === 'fehler' ? 'Fehler' : 'Hinweis'} · ${esc(BEREICHE[b.bereich] || b.bereich)}</span>
         ${esc(b.beschreibung)}${b.vorschlag ? `<br><em>Vorschlag:</em> ${esc(b.vorschlag)}` : ''}</li>`).join('')}</ul>` : ''),
        d.urteil === 'fehler_gefunden' ? 'fehler' : 'ok');
    },
    async tags() {
      const f = formular();
      if (!f.text.trim()) return zeigen('Zuerst einen Aufgabentext erfassen.', 'fehler');
      const d = await anfrage('tags', f);
      if (!d) return;
      const markieren = (name, werte) => werte.forEach(v => {
        const box = form.querySelector(`input[name=${name}][value="${CSS.escape(String(v))}"]`);
        if (!box) return;
        box.checked = true;
        const zeile = box.closest('label'); zeile.classList.add('ki-vorschlag');
        const det = box.closest('details'); if (det) det.open = true;
      });
      form.querySelectorAll('.ki-vorschlag').forEach(x => x.classList.remove('ki-vorschlag'));
      markieren('thema', d.themen); markieren('lernziel', d.lernziele); markieren('bivo', d.bivo);
      if (d.k_stufe) form.querySelector('[name=k_stufe]').value = String(d.k_stufe);
      form.querySelector('.auswahl').dispatchEvent(new Event('change', { bubbles: true }));
      zeigen(`✅ Vorschlag markiert (gelb hinterlegt): ${d.themen.length} Thema/Themen, ${d.lernziele.length} Lernziel(e),
        ${d.bivo.length} BiVo-Code(s), K${esc(d.k_stufe)}.<p class="muted">${esc(d.begruendung)}</p>`, 'ok');
    },
    async variante() {
      const d = await anfrage('variante', { ...formular(), art: wert('#ki-variante') });
      if (!d) return;
      aufgabeEinsetzen(d.aufgabe);
      // als neue Aufgabe speichern; Grafiken der Ausgangsaufgabe übernehmen
      form.action = panel.dataset.neuUrl;
      if (!form.querySelector('[name=bilder_von]')) {
        const h = document.createElement('input'); h.type = 'hidden'; h.name = 'bilder_von'; h.value = panel.dataset.aufgabeId;
        form.appendChild(h);
      }
      document.querySelector('h1').innerHTML = 'Neue Aufgabe <span class="badge">KI-Variante</span>';
      zeigen(`✅ Variante eingesetzt. Beim Speichern entsteht eine <strong>neue</strong> Aufgabe (mit den Grafiken des Originals).${hinweisListe(d.hinweise)}`, 'ok');
    },
  };
  panel.querySelectorAll('[data-ki-start]').forEach(b => b.addEventListener('click', () => AKTIONEN[b.dataset.kiStart]()));
})();
