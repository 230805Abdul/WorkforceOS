// Apply the saved light/dark theme before the first paint (avoids a flash). A separate file, not an inline <script>,
// so the Content-Security-Policy can forbid ALL inline scripts (the main defence against injected JavaScript).
try {
  var t = localStorage.getItem("wos-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = t;
} catch (e) {
  /* storage blocked: the default theme is used */
}
