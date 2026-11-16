// Gemeinsame Funktionen jeder Seite (keine Inline-Skripte wegen Content-Security-Policy)
(function () {
  window.CSRF = document.querySelector('meta[name=csrf-token]').content;

  // Hell/Dunkel umschalten; ohne eigene Wahl der Systemeinstellung folgen
  var root = document.documentElement, knopf = document.getElementById('theme-toggle');
  function beschriften() {
    if (!knopf) return;
    var dunkel = root.dataset.theme === 'dark';
    var text = dunkel ? 'Helles Design' : 'Dunkles Design';
    knopf.title = text; knopf.setAttribute('aria-label', text);
    var span = knopf.querySelector('span'); if (span) span.textContent = text;
  }
  if (knopf) knopf.addEventListener('click', function () {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('theme', root.dataset.theme); } catch (e) { /* ignorieren */ }
    beschriften();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
    var gewaehlt = null;
    try { gewaehlt = localStorage.getItem('theme'); } catch (x) { /* ignorieren */ }
    if (!gewaehlt) { root.dataset.theme = e.matches ? 'dark' : 'light'; beschriften(); }
  });
  beschriften();

  // Rückfragen vor Löschaktionen: <form data-bestaetigen="…"> bzw. <button data-bestaetigen="…">
  document.addEventListener('submit', function (e) {
    var f = e.target, btn = e.submitter;
    var frage = (btn && btn.dataset.bestaetigen) || f.dataset.bestaetigen;
    if (frage && !confirm(frage)) e.preventDefault();
  });

  // Navigation auf kleinen Bildschirmen
  var nav = document.getElementById('navleiste'), schleier = document.getElementById('nav-schleier');
  var oeffnen = document.getElementById('nav-oeffnen');
  function zeige(an) { document.body.classList.toggle('nav-offen', an); }
  if (oeffnen) oeffnen.addEventListener('click', function () { zeige(true); });
  if (schleier) schleier.addEventListener('click', function () { zeige(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') zeige(false); });
})();
