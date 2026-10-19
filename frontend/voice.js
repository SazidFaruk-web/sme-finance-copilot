// Speech only edits the field. Sending remains the owner's explicit action.
export function createVoiceButton({ h, input, language = "en", Speech = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition }) {
  const text = {
    en: ["Use voice; review the text before sending", "Voice input is unavailable; you can type instead"],
    bn: ["কথা বলে লিখুন; পাঠানোর আগে লেখা মিলিয়ে নিন", "কথা লেখা যাচ্ছে না; টাইপ করতে পারেন"],
    zh: ["语音输入；发送前请检查文字", "语音输入不可用，您可以直接输入"],
  }[language] || ["Use voice; review the text before sending", "Voice input is unavailable; you can type instead"];
  const button = h("button", { type: "button", class: "btn mic", disabled: !Speech, title: Speech ? text[0] : text[1], "aria-label": Speech ? text[0] : text[1] }, "🎤");
  let recognition = null;
  const stop = () => { recognition = null; button.classList.remove("on"); };
  button.addEventListener("click", () => {
    if (recognition) { recognition.stop(); return; }
    recognition = new Speech();
    recognition.lang = { bn: "bn-BD", zh: "zh-CN" }[language] || "en-US";
    recognition.interimResults = false;
    recognition.onresult = event => {
      const transcript = event.results[0][0].transcript;
      input.value = [input.value.trim(), transcript.trim()].filter(Boolean).join(" ");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    };
    recognition.onend = stop;
    recognition.onerror = () => { button.title = text[1]; stop(); input.focus(); };
    button.classList.add("on");
    try { recognition.start(); } catch { button.title = text[1]; stop(); input.focus(); }
  });
  return button;
}
