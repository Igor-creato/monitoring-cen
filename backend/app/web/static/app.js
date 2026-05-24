document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches("[data-loading]")) {
    return;
  }

  form.classList.add("is-submitting");
  window.setTimeout(() => {
    for (const button of form.querySelectorAll("button[type='submit']")) {
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
    }
  }, 0);
});
