// Authentication has one active interface language. Credentials and business names are user data.
import { zhCopy } from "./i18n-zh.js?v=2";

export const AUTH_COPY = {
  en: {
    brand: "SME Copilot", language: "Language", loginTitle: "Welcome back.", loginIntro: "A little clarity for your business starts here.",
    signupTitle: "Start with the essentials.", signupIntro: "Create an account for your business. We’ll help you take the next step.",
    username: "Username", usernamePlaceholder: "Enter your username", password: "Password", passwordPlaceholder: "Enter your password",
    business: "Business name", businessPlaceholder: "e.g. Rina’s shop", name: "Your name", namePlaceholder: "Enter your full name",
    newUsernamePlaceholder: "Choose a username", usernameHint: "Use English letters, numbers, dots, hyphens or underscores.",
    newPasswordPlaceholder: "Create a password", passwordHint: "Use at least 8 characters.", confirm: "Confirm password", confirmPlaceholder: "Enter the password again",
    show: "Show", hide: "Hide", showPassword: "Show password", hidePassword: "Hide password", showConfirm: "Show confirmed password", hideConfirm: "Hide confirmed password",
    login: "Log in", signup: "Create account", loggingIn: "Logging in…", creating: "Creating your account…",
    newHere: "New here?", already: "Already have an account?", footer: "Your business. One step at a time.",
    demo: "Try a demo account", demoHint: "Choose an account to fill the form, then log in.", owner: "Business owner", accountant: "Accountant", viewer: "View only",
    checkFields: "Check the highlighted fields and try again.", requiredUsername: "Enter your username.", requiredPassword: "Enter your password.",
    requiredBusiness: "Enter your business name.", shortBusiness: "Use at least 2 characters for the business name.", requiredName: "Enter your name.",
    usernameFormat: "Use 3–40 English letters, numbers, dots, hyphens or underscores.", shortPassword: "Use at least 8 characters for your password.",
    requiredConfirm: "Enter your password again.", mismatch: "The passwords don’t match. Please check them.",
    invalidCredentials: "The username or password isn’t correct. Please try again.", usernameTaken: "That username is already in use. Choose another one.",
    locked: "Too many unsuccessful attempts. Try again in 15 minutes.", rateLimited: "Too many attempts. Please wait a little before trying again.",
    signupDisabled: "New accounts are currently unavailable. Log in with an existing account.", expired: "Your session ended. Please log in again.",
    network: "We couldn’t connect. Check your connection and try again.", unavailable: "We couldn’t reach the service. Please try again shortly.",
    invalidDetails: "Some details couldn’t be accepted. Please check the form and try again.", generic: "We couldn’t continue. Please try again.",
  },
  bn: {
    brand: "এসএমই কোপাইলট", language: "ভাষা", loginTitle: "আবারও স্বাগতম।", loginIntro: "আপনার ব্যবসার সহজ হিসাব শুরু হোক এখানেই।",
    signupTitle: "সহজভাবে শুরু করুন।", signupIntro: "আপনার ব্যবসার জন্য একটি অ্যাকাউন্ট খুলুন। পরের কাজে আমরা সাহায্য করব।",
    username: "ব্যবহারকারী নাম", usernamePlaceholder: "ব্যবহারকারী নাম লিখুন", password: "পাসওয়ার্ড", passwordPlaceholder: "পাসওয়ার্ড লিখুন",
    business: "ব্যবসার নাম", businessPlaceholder: "যেমন: রিনার দোকান", name: "আপনার নাম", namePlaceholder: "আপনার পুরো নাম লিখুন",
    newUsernamePlaceholder: "একটি ব্যবহারকারী নাম বেছে নিন", usernameHint: "ইংরেজি অক্ষর, সংখ্যা, ডট, হাইফেন বা আন্ডারস্কোর ব্যবহার করুন।",
    newPasswordPlaceholder: "একটি পাসওয়ার্ড তৈরি করুন", passwordHint: "অন্তত ৮টি অক্ষর বা চিহ্ন ব্যবহার করুন।", confirm: "পাসওয়ার্ড নিশ্চিত করুন", confirmPlaceholder: "পাসওয়ার্ডটি আবার লিখুন",
    show: "দেখুন", hide: "লুকান", showPassword: "পাসওয়ার্ড দেখুন", hidePassword: "পাসওয়ার্ড লুকান", showConfirm: "নিশ্চিত করা পাসওয়ার্ড দেখুন", hideConfirm: "নিশ্চিত করা পাসওয়ার্ড লুকান",
    login: "লগ ইন", signup: "অ্যাকাউন্ট খুলুন", loggingIn: "লগ ইন হচ্ছে…", creating: "অ্যাকাউন্ট তৈরি হচ্ছে…",
    newHere: "প্রথমবার এসেছেন?", already: "আগে থেকেই অ্যাকাউন্ট আছে?", footer: "আপনার ব্যবসা। একবারে একটি কাজ।",
    demo: "ডেমো অ্যাকাউন্ট ব্যবহার করুন", demoHint: "একটি অ্যাকাউন্ট বেছে নিয়ে ফর্ম পূরণ করুন, তারপর লগ ইন করুন।", owner: "ব্যবসার মালিক", accountant: "হিসাবরক্ষক", viewer: "শুধু দেখার অনুমতি",
    checkFields: "চিহ্নিত ঘরগুলো দেখে আবার চেষ্টা করুন।", requiredUsername: "আপনার ব্যবহারকারী নাম লিখুন।", requiredPassword: "আপনার পাসওয়ার্ড লিখুন।",
    requiredBusiness: "আপনার ব্যবসার নাম লিখুন।", shortBusiness: "ব্যবসার নাম অন্তত ২টি অক্ষরের হতে হবে।", requiredName: "আপনার নাম লিখুন।",
    usernameFormat: "৩ থেকে ৪০টি ইংরেজি অক্ষর, সংখ্যা, ডট, হাইফেন বা আন্ডারস্কোর ব্যবহার করুন।", shortPassword: "পাসওয়ার্ডে অন্তত ৮টি অক্ষর বা চিহ্ন ব্যবহার করুন।",
    requiredConfirm: "পাসওয়ার্ডটি আবার লিখুন।", mismatch: "পাসওয়ার্ড দুটি মেলেনি। আবার মিলিয়ে নিন।",
    invalidCredentials: "ব্যবহারকারী নাম বা পাসওয়ার্ড সঠিক নয়। আবার চেষ্টা করুন।", usernameTaken: "এই ব্যবহারকারী নামটি আগে থেকেই ব্যবহার হচ্ছে। অন্য একটি বেছে নিন।",
    locked: "অনেকবার ভুল তথ্য দেওয়া হয়েছে। ১৫ মিনিট পরে আবার চেষ্টা করুন।", rateLimited: "অনেকবার চেষ্টা করা হয়েছে। একটু অপেক্ষা করে আবার চেষ্টা করুন।",
    signupDisabled: "এখন নতুন অ্যাকাউন্ট খোলা যাচ্ছে না। আগের অ্যাকাউন্ট দিয়ে লগ ইন করুন।", expired: "আপনার সেশনের সময় শেষ হয়েছে। আবার লগ ইন করুন।",
    network: "সংযোগ করা যায়নি। ইন্টারনেট সংযোগ দেখে আবার চেষ্টা করুন।", unavailable: "সেবাটির সঙ্গে সংযোগ করা যায়নি। একটু পরে আবার চেষ্টা করুন।",
    invalidDetails: "কিছু তথ্য গ্রহণ করা যায়নি। ফর্মটি দেখে আবার চেষ্টা করুন।", generic: "এগোনো যায়নি। আবার চেষ্টা করুন।",
  },
};
AUTH_COPY.zh = zhCopy(AUTH_COPY.en);

export function validateAuth(mode, values) {
  const errors = {};
  const username = (values.username || "").trim();
  if (!username) errors.username = "requiredUsername";
  if (!values.password) errors.password = "requiredPassword";
  if (mode === "signup") {
    if (!values.business?.trim()) errors.business = "requiredBusiness";
    else if (Array.from(values.business.trim()).length < 2) errors.business = "shortBusiness";
    if (!values.name?.trim()) errors.name = "requiredName";
    if (username && !/^[A-Za-z0-9._-]{3,40}$/.test(username)) errors.username = "usernameFormat";
    if (values.password && Array.from(values.password).length < 8) errors.password = "shortPassword";
    if (!values.confirm) errors.confirm = "requiredConfirm";
    else if (values.password !== values.confirm) errors.confirm = "mismatch";
  }
  return errors;
}

// Display localized messages rather than raw English API details or validation JSON.
export function authErrorKey(error) {
  const message = String(error?.message || error || "").toLowerCase();
  if (message.includes("locked")) return "locked";
  if (error?.status === 429 || message.includes("rate limit")) return "rateLimited";
  if (message.includes("expired") || message.includes("please log in again")) return "expired";
  if (error?.status === 401 || message.includes("invalid username or password")) return "invalidCredentials";
  if (error?.status === 409) return "usernameTaken";
  if (error?.status === 403) return "signupDisabled";
  if (error?.status === 422) return "invalidDetails";
  if (error instanceof TypeError || /failed to fetch|network|connection|load failed/.test(message)) return "network";
  if (error?.status >= 500) return "unavailable";
  return "generic";
}
