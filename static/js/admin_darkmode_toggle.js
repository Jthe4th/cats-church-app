(function () {
  const STORAGE_KEY = "welcome_admin_theme";
  const DARK_LINK_ID = "jazzmin-dark-mode-theme";

  function getStoredPreference() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function setStoredPreference(value) {
    try {
      if (value) {
        window.localStorage.setItem(STORAGE_KEY, value);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch (e) {
      // Ignore localStorage errors; theme will still work for the session.
    }
  }

  function isSystemDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function isDarkEnabled(preference) {
    if (preference === "dark") {
      return true;
    }
    if (preference === "light") {
      return false;
    }
    return isSystemDark();
  }

  function applyTheme(preference) {
    const darkLink = document.getElementById(DARK_LINK_ID);
    if (!darkLink) {
      return;
    }
    const darkEnabled = isDarkEnabled(preference);
    document.body.classList.toggle("dark-mode", darkEnabled);
    document.documentElement.classList.toggle("dark-mode", darkEnabled);
    if (preference === "dark") {
      darkLink.media = "all";
      return;
    }
    if (preference === "light") {
      darkLink.media = "not all";
      return;
    }
    darkLink.media = "(prefers-color-scheme: dark)";
  }

  function buildToggleButton() {
    const rightNav = document.querySelector("#jazzy-navbar .navbar-nav.ml-auto");
    if (!rightNav || document.getElementById("welcome-admin-darkmode-toggle")) {
      return null;
    }

    const item = document.createElement("li");
    item.className = "nav-item";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "nav-link btn";
    button.id = "welcome-admin-darkmode-toggle";
    button.setAttribute("aria-label", "Toggle dark mode");

    const icon = document.createElement("span");
    icon.id = "welcome-admin-darkmode-icon";
    icon.textContent = "🌙";
    icon.style.fontSize = "1.05rem";
    icon.style.lineHeight = "1";
    icon.setAttribute("aria-hidden", "true");

    button.appendChild(icon);
    item.appendChild(button);
    rightNav.insertBefore(item, rightNav.firstChild);
    return button;
  }

  function syncButtonState(button, preference) {
    const icon = document.getElementById("welcome-admin-darkmode-icon");
    if (!button || !icon) {
      return;
    }
    if (isDarkEnabled(preference)) {
      button.title = "Dark mode on (click for light mode)";
    } else {
      button.title = "Dark mode off (click for dark mode)";
    }
  }

  function init() {
    if (!document.getElementById(DARK_LINK_ID)) {
      return;
    }

    const button = buildToggleButton();
    let preference = getStoredPreference();
    applyTheme(preference);
    syncButtonState(button, preference);

    if (button) {
      button.addEventListener("click", function () {
        const next = isDarkEnabled(preference) ? "light" : "dark";
        preference = next;
        setStoredPreference(next);
        applyTheme(preference);
        syncButtonState(button, preference);
      });
    }

    if (window.matchMedia) {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      media.addEventListener("change", function () {
        if (!getStoredPreference()) {
          applyTheme(null);
          syncButtonState(button, null);
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
