// Farbschema vor dem ersten Rendern setzen (kein Aufblitzen): gespeicherte Wahl, sonst Systemeinstellung
(function () {
  var t = null;
  try { t = localStorage.getItem('theme'); } catch (e) { /* privater Modus */ }
  if (t !== 'light' && t !== 'dark') t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.dataset.theme = t;
})();
