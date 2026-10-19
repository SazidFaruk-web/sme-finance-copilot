from types import SimpleNamespace

from sme_copilot.greeting import clean, make_greeting


class Fake:
    def __init__(self, text="", adapter="openai", boom=False):
        self.adapter, self.text, self.boom, self.seen = adapter, text, boom, None

    def chat(self, msgs, **kw):
        self.seen = msgs
        if self.boom:
            raise RuntimeError("model offline")
        return SimpleNamespace(content=self.text)


GOOD = "Hey Rafi, I'm your AI Assistant for business money, ask me about sales, costs or cash flow anytime."


def test_returns_model_text_and_prompt_has_no_religious_greeting():
    p = Fake(GOOD)
    assert make_greeting("Rafi Ahmed", "en", provider=p) == GOOD
    sys_prompt = p.seen[0].content
    assert "Do not use a religious greeting" in sys_prompt and "English" in sys_prompt
    assert "Rafi" in p.seen[1].content and "Ahmed" not in p.seen[1].content


def test_fallbacks_return_none():
    assert make_greeting("A", provider=Fake(adapter="rules")) is None
    assert make_greeting("A", provider=Fake(boom=True)) is None
    assert make_greeting("A", provider=Fake("ok")) is None  # too short


def test_clean_strips_markup_and_rejects_greeting_or_links():
    assert clean('**"Hi, I am your AI Assistant for business money, ask me anything."**') == \
        "Hi, I am your AI Assistant for business money, ask me anything."
    assert clean("Assalamu alaikum! I am your AI Assistant for business money.") is None
    assert clean("Visit https://example.com for your AI Assistant for business money.") is None
