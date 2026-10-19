import { icon } from "./icons.js?v=12";
import { AUTH_COPY, validateAuth, authErrorKey } from "./auth-copy.js?v=18";

// "More languages" (owner decision 2026-10-19): English by default; the owner can show বাংলা and 中文 on this device.
const MORE_KEY = "more_languages";
export const moreLanguages = () => { try { return localStorage.getItem(MORE_KEY) === "1"; } catch { return false; } };
export const setMoreLanguages = on => { try { localStorage.setItem(MORE_KEY, on ? "1" : ""); } catch { /* private mode */ } };

export function renderAuth(root, { h, language, health, api, onLanguage, onAuthenticated, initialError, startMode = "login" }) {
  const state = {
    language: ["bn", "zh"].includes(language) && moreLanguages() && (health.languages || ["en"]).includes(language) ? language : "en", mode: health.allow_signup !== false && startMode === "signup" ? "signup" : "login",
    allowSignup: health.allow_signup !== false, busy: false, error: initialError ? authErrorKey(initialError) : "", fields: {},
    drafts: { login: { username: "", password: "" }, signup: { business: "", name: "", username: "", password: "", confirm: "" } },
    visible: {}, demoOpen: false,
  };

  function captureDraft() {
    const form = root.querySelector(".auth-form");
    if (form) Object.assign(state.drafts[state.mode], Object.fromEntries(new FormData(form)));
  }

  function draw(focusId) {
    const c = AUTH_COPY[state.language], signup = state.mode === "signup", values = state.drafts[state.mode];
    document.documentElement.lang = state.language === "zh" ? "zh-CN" : state.language;
    document.title = `${signup ? c.signup : c.login} · ${c.brand}`;
    const field = (key, label, placeholder, props = {}, hint = "") => {
      const id = `auth-${key}`, errorId = `${id}-error`, hintId = `${id}-hint`, password = ["password", "confirm"].includes(key);
      const input = h("input", { id, name: key, type: password && !state.visible[key] ? "password" : "text", value: values[key] || "", placeholder,
        required: true, disabled: state.busy, "aria-invalid": state.fields[key] ? "true" : null,
        "aria-describedby": [hint ? hintId : "", state.fields[key] ? errorId : ""].filter(Boolean).join(" ") || null,
        ...props, oninput: e => {
          values[key] = e.target.value;
          if (state.fields[key]) {
            delete state.fields[key]; input.removeAttribute("aria-invalid");
            input.setAttribute("aria-describedby", hint ? hintId : "");
            root.querySelector(`#${errorId}`)?.remove();
          }
        } });
      const toggle = !password ? null : h("button", { class: "auth-reveal", type: "button", disabled: state.busy,
        "aria-controls": id, "aria-pressed": String(!!state.visible[key]),
        "aria-label": key === "confirm" ? (state.visible[key] ? c.hideConfirm : c.showConfirm) : (state.visible[key] ? c.hidePassword : c.showPassword),
        onclick: e => {
          state.visible[key] = !state.visible[key]; input.type = state.visible[key] ? "text" : "password";
          e.currentTarget.textContent = state.visible[key] ? c.hide : c.show;
          e.currentTarget.setAttribute("aria-pressed", String(!!state.visible[key]));
          e.currentTarget.setAttribute("aria-label", key === "confirm" ? (state.visible[key] ? c.hideConfirm : c.showConfirm) : (state.visible[key] ? c.hidePassword : c.showPassword));
        } }, state.visible[key] ? c.hide : c.show);
      return h("div", { class: "auth-field" }, h("label", { for: id }, label),
        h("div", { class: password ? "auth-password" : "auth-input" }, input, toggle),
        hint ? h("p", { class: "auth-hint", id: hintId }, hint) : null,
        state.fields[key] ? h("p", { class: "auth-field-error", id: errorId }, c[state.fields[key]]) : null);
    };
    const form = h("form", { class: "auth-form", novalidate: true, "aria-label": signup ? c.signup : c.login, "aria-busy": String(state.busy), onsubmit: async e => {
      e.preventDefault(); if (state.busy) return;
      // Password managers may fill DOM values without dispatching input events.
      Object.assign(values, Object.fromEntries(new FormData(e.currentTarget)));
      state.fields = validateAuth(state.mode, values);
      if (Object.keys(state.fields).length) {
        state.error = "checkFields";
        const order = signup ? ["business", "name", "username", "password", "confirm"] : ["username", "password"];
        draw(`auth-${order.find(key => state.fields[key])}`); return;
      }
      state.error = ""; state.busy = true; draw();
      try {
        const body = signup ? { business_name: values.business.trim(), full_name: values.name.trim(), username: values.username.trim(), password: values.password }
          : { username: values.username.trim(), password: values.password };
        await api(signup ? "/api/auth/signup" : "/api/auth/login", { body });
        await onAuthenticated();
      } catch (error) {
        state.error = authErrorKey(error);
        if (state.error === "usernameTaken") state.fields.username = "usernameTaken";
        if (state.error === "signupDisabled") { state.allowSignup = false; state.mode = "login"; }
        state.busy = false; draw("auth-message");
      }
    } },
      signup ? field("business", c.business, c.businessPlaceholder, { autocomplete: "organization", maxlength: 120 }) : null,
      signup ? field("name", c.name, c.namePlaceholder, { autocomplete: "name", maxlength: 120 }) : null,
      field("username", c.username, signup ? c.newUsernamePlaceholder : c.usernamePlaceholder,
        { autocomplete: "username", autocapitalize: "none", spellcheck: "false", maxlength: signup ? 40 : 80 }, signup ? c.usernameHint : ""),
      field("password", c.password, signup ? c.newPasswordPlaceholder : c.passwordPlaceholder,
        { autocomplete: signup ? "new-password" : "current-password", maxlength: 200 }, signup ? c.passwordHint : ""),
      signup ? field("confirm", c.confirm, c.confirmPlaceholder, { autocomplete: "new-password", maxlength: 200 }) : null,
      state.error ? h("p", { class: "auth-message", id: "auth-message", role: "alert", tabindex: -1 }, c[state.error]) : null,
      h("button", { class: "auth-submit", type: "submit", disabled: state.busy }, state.busy ? h("span", { class: "auth-spinner", "aria-hidden": "true" }) : null,
        state.busy ? (signup ? c.creating : c.loggingIn) : (signup ? c.signup : c.login), state.busy ? null : icon("arrow", 18)));
    const switchMode = mode => { if (state.busy) return; captureDraft(); state.mode = mode; state.error = ""; state.fields = {}; state.visible = {}; draw("auth-heading"); };
    const languages = h("div", { class: "auth-languages", role: "group", "aria-label": c.language }, [["en", "English"], ["bn", "বাংলা"], ["zh", "中文"]].filter(([code]) => (health.languages || ["en"]).includes(code)).map(([code, text]) => h("button", {
      type: "button", id: `auth-lang-${code}`, lang: code, "aria-pressed": String(state.language === code), disabled: state.busy,
      onclick: () => { captureDraft(); state.language = code; onLanguage(code); draw(`auth-lang-${code}`); },
    }, text)));
    const demo = !health.demo_users?.length ? null : h("details", { class: "auth-demo", open: state.demoOpen, ontoggle: e => { state.demoOpen = e.currentTarget.open; } },
      h("summary", {}, c.demo), h("p", {}, c.demoHint), h("div", { class: "auth-demo-choices" }, health.demo_users.map(d => h("button", {
        type: "button", disabled: state.busy, onclick: () => {
          state.drafts.login = { username: d.username, password: d.password }; state.mode = "login"; state.error = ""; state.fields = {}; state.visible = {}; draw("auth-password");
        },
      }, d.name ? `${d.name} · ${d.business}${d.note ? ` (${d.note})` : ""}` : (c[d.role] || c.viewer)))));
    const screen = h("div", { class: "auth-screen" },
      h("header", { class: "auth-header" }, h("div", { class: "auth-brand" }, h("img", { class: "auth-brand-mark", src: "/static/app-icon.svg?v=2", alt: "" }), h("span", {}, c.brand)), (health.languages || ["en"]).length > 1 && moreLanguages() ? languages : null),
      h("main", { class: "auth-main" }, h("section", { class: "auth-card", "aria-labelledby": "auth-heading" },
        h("div", { class: "auth-heading" }, h("h1", { id: "auth-heading", tabindex: -1 }, signup ? c.signupTitle : c.loginTitle), h("p", {}, signup ? c.signupIntro : c.loginIntro)),
        form,
        state.allowSignup ? h("p", { class: "auth-switch" }, signup ? c.already : c.newHere, " ", h("button", { type: "button", disabled: state.busy, onclick: () => switchMode(signup ? "login" : "signup") }, signup ? c.login : c.signup)) : null,
        !signup ? demo : null,
        (health.languages || ["en"]).length > 1 ? h("p", { class: "auth-more-langs" }, h("button", { type: "button", id: "auth-more-langs",
          disabled: state.busy, onclick: () => {
            const on = !moreLanguages(); setMoreLanguages(on); captureDraft();
            if (!on && state.language !== "en") { state.language = "en"; onLanguage("en"); }
            draw("auth-more-langs");
          } }, moreLanguages() ? c.fewerLanguages : c.moreLanguages)) : null)),
      h("footer", { class: "auth-footer" }, c.footer));
    root.replaceChildren(screen);
    if (focusId) root.querySelector(`#${focusId}`)?.focus();
  }
  draw();
}
