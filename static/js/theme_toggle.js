// theme-toggle.js - localStorage pro toggle rápido do header,
// window.__settings (Settings > Customização) como default de inicialização,
// com suporte a "Sistema" (segue prefers-color-scheme, reage ao vivo).

(function() {
    const htmlElement   = document.documentElement;
    const media         = window.matchMedia('(prefers-color-scheme: dark)');

    const savedMode    = localStorage.getItem('theme'); // 'light' | 'dark' | null
    const settingsMode = (window.__settings && window.__settings['theme.mode']) || 'dark';

    let followSystem = false;
    let dark_mode;

    if (savedMode === 'light' || savedMode === 'dark') {
        dark_mode = savedMode === 'dark';
    } else if (settingsMode === 'system') {
        followSystem = true;
        dark_mode = media.matches;
    } else {
        dark_mode = settingsMode === 'dark';
    }

    function applyTheme(isDark) {
        dark_mode = isDark;
        htmlElement.setAttribute('data-bs-theme', isDark ? 'dark' : 'light');
    }

    applyTheme(dark_mode);

    if (followSystem) {
        media.addEventListener('change', (e) => {
            if (followSystem) applyTheme(e.matches);
        });
    }

    function setTheme(isDark) {
        // Clique explícito no toggle sempre sai do modo "Sistema" pra essa sessão —
        // trocar o modo de volta só é feito em Settings.
        followSystem = false;
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        applyTheme(isDark);
    }

    // Duas instâncias no DOM (header desktop + drawer mobile) — a do drawer
    // (aside.html) só é parseada DEPOIS deste <script> (incluído ainda
    // dentro de header.html), então busca os botões só depois do DOM
    // completo, senão essa instância fica sem listener nenhum.
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => setTheme(!dark_mode));
        });
    });

    window.dark_mode = dark_mode;
    window.setTheme = setTheme;
})();
