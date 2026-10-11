# -*- coding: utf-8 -*-
"""
مُعرِّب المصطلحات العلمية
اكتب مصطلحاً بالإنجليزية أو بالعربية المعرَّبة صوتياً (مثل: ميتوكوندريا)
فيعطيك: الإنجليزية + التعريب النصفي + التعريب العربي الكامل.

ملف واحد فقط. المتطلبات (ضعها في ملف requirements.txt عند النشر):
    streamlit
    openai>=1.55
    httpx
"""

import html
import json
import os

import httpx
import streamlit as st
import streamlit.components.v1 as components
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

MAX_TERMS = 15  # حد أعلى لعدد المصطلحات في الطلب الواحد لضبط التكلفة

# =========================================================
# 1. إعداد الصفحة والتصميم
# =========================================================
st.set_page_config(
    page_title="مُعرِّب المصطلحات العلمية",
    page_icon="🔬",
    layout="centered",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Cairo', sans-serif !important; }
.block-container { max-width: 800px; padding-top: 1.5rem; }
.app-title { text-align: center; color: #1E3A8A; font-weight: 800; font-size: 2.1rem; margin-bottom: 0.3rem; }
.subtitle { text-align: center; color: #4B5563; font-size: 1.05rem; line-height: 1.8; margin-bottom: 1.5rem; }
div.stButton > button {
    width: 100%; background-color: #1E3A8A; color: white !important; border: none;
    border-radius: 8px; padding: 0.75rem; font-family: 'Cairo', sans-serif;
    font-size: 1.1rem; font-weight: 700; transition: all 0.3s ease;
}
div.stButton > button:hover { background-color: #1D4ED8; box-shadow: 0 4px 12px rgba(29,78,216,0.3); }
.stTextArea textarea {
    direction: rtl !important; text-align: right !important;
    font-family: 'Cairo', sans-serif !important; font-size: 1.1rem !important; border-radius: 8px;
}
.term-card {
    background: #F8FAFC; border-right: 5px solid #1E3A8A; border-radius: 8px;
    padding: 16px; margin: 14px 0 4px 0; direction: rtl; text-align: right;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); line-height: 2.1; color: #111827; font-size: 1.1rem;
}
.term-card .lbl { color: #6B7280; font-size: 0.95rem; }
.term-card .full { color: #047857; font-weight: 800; font-size: 1.3rem; }
.term-card .en { direction: ltr; display: inline-block; font-weight: 700; }
.note-card {
    background: #FEF3C7; border-right: 5px solid #F59E0B; border-radius: 8px;
    padding: 12px 16px; margin: 14px 0; direction: rtl; text-align: right; color: #78350F;
}
.footer { text-align: center; color: #6B7280; font-size: 0.9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# =========================================================
# 2. الترويسة
# =========================================================
st.markdown('<div class="app-title">🔬 مُعرِّب المصطلحات العلمية</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">اكتب المصطلح بالإنجليزية، أو بالعربية المعرَّبة صوتياً (مثل: ميتوكوندريا)، '
    'وستحصل على الإنجليزية والتعريب النصفي والتعريب العربي الكامل.</div>',
    unsafe_allow_html=True,
)

# =========================================================
# 3. تعليمات النموذج
# =========================================================
SYSTEM_PROMPT = """
أنت لغوي عربي متخصص في المصطلح العلمي. سيعطيك المستخدم مصطلحاً علمياً واحداً أو أكثر
(كل مصطلح في سطر). يكون كل مصطلح إما:
 (أ) إنجليزياً، مثل: mitochondria
 (ب) عربياً معرَّباً صوتياً (تعريب نصفي)، مثل: ميتوكوندريا

لكل مصطلح أعطِ هذه الحقول دائماً، مهما كانت لغة الإدخال:
 1. english: المصطلح الإنجليزي الصحيح بحروف لاتينية.
 2. semi_arabic: التعريب النصفي، أي نقل الصوت بحروف عربية (مثل: ميتوكوندريا).
 3. full_arabic: التعريب الكامل، أي بديل عربي أصيل مشتق من وظيفة الشيء أو جوهره
    (كلمة واحدة أو مضاف ومضاف إليه). إن وُجد مصطلح عربي معروف ومستعمل فاستعمله أولاً،
    وإلا فاشتق بديلاً واضحاً.
 4. reason: سطر واحد يشرح سبب اختيار البديل الكامل.

إن كان الإدخال غير مفهوم أو ليس مصطلحاً علمياً، ضع "ok": false وفي "reason" سبب مختصر،
واترك بقية الحقول فارغة. أعد مصطلحاً واحداً في النتيجة لكل سطر إدخال وبالترتيب نفسه.

أخرج JSON فقط بهذا الشكل بالضبط:
{
  "terms": [
    {"input": "ما كتبه المستخدم", "ok": true, "english": "", "semi_arabic": "", "full_arabic": "", "reason": ""}
  ]
}
"""

# =========================================================
# 4. مفتاح API والإعدادات
# =========================================================
def get_api_key() -> str:
    """يقرأ المفتاح من Streamlit Secrets، وإلا من متغيرات البيئة."""
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY", "").strip()


api_key = get_api_key()

with st.expander("⚙️ الإعدادات", expanded=not api_key):
    if api_key:
        st.success("🔐 تم تحميل مفتاح API.")
    else:
        api_key = st.text_input(
            "مفتاح OpenAI API",
            type="password",
            help="أدخل مفتاحك هنا، أو ضعه في Secrets باسم OPENAI_API_KEY.",
        ).strip()
    model_name = st.selectbox("طراز المعالجة:", ["gpt-4o", "gpt-4o-mini"], index=0)

# =========================================================
# 5. المدخلات
# =========================================================
if "results" not in st.session_state:
    st.session_state.results = None

user_input = st.text_area(
    "المصطلحات",
    height=140,
    placeholder="اكتب مصطلحاً في كل سطر، مثل:\nmitochondria\nميتوكوندريا\nelectron",
    label_visibility="collapsed",
)

# =========================================================
# 6. التنفيذ
# =========================================================
def as_bool(value) -> bool:
    """يتعامل مع حالة إرجاع النموذج 'false' كنص بدل قيمة منطقية."""
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "")
    return bool(value)


def parse_model_json(raw: str) -> list:
    """يحوّل رد النموذج إلى قائمة مصطلحات، ويتحمل أسوار ```json."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    items = []
    for t in data.get("terms", []) or []:
        if not isinstance(t, dict):
            continue
        item = {
            "input": str(t.get("input", "")).strip(),
            "ok": as_bool(t.get("ok", True)),
            "english": str(t.get("english", "")).strip(),
            "semi_arabic": str(t.get("semi_arabic", "")).strip(),
            "full_arabic": str(t.get("full_arabic", "")).strip(),
            "reason": str(t.get("reason", "")).strip(),
        }
        # نتيجة "ناجحة" لكنها بلا بديل كامل = غير صالحة
        if item["ok"] and not item["full_arabic"]:
            item["ok"] = False
            item["reason"] = item["reason"] or "لم أستطع إيجاد بديل لهذا المصطلح."
        items.append(item)
    return items


if st.button("🚀 عرِّب المصطلح"):
    lines_in = [line.strip() for line in user_input.splitlines() if line.strip()]
    if not api_key:
        st.error("❌ أدخل مفتاح OpenAI API في قسم «الإعدادات» أعلاه.")
    elif not lines_in:
        st.warning("⚠️ اكتب مصطلحاً واحداً على الأقل.")
    else:
        if len(lines_in) > MAX_TERMS:
            st.warning(f"⚠️ سأعالج أول {MAX_TERMS} مصطلحاً فقط.")
            lines_in = lines_in[:MAX_TERMS]
        with st.spinner("🔄 جاري التعريب..."):
            try:
                client = OpenAI(api_key=api_key, timeout=httpx.Timeout(60.0, connect=10.0))
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": "\n".join(lines_in)},
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                items = parse_model_json(content)
                if items:
                    st.session_state.results = items
                else:
                    st.error("❌ لم يرجع المحرك نتائج. أعد المحاولة.")
            except json.JSONDecodeError:
                st.error("❌ تعذر فهم رد المحرك. أعد المحاولة.")
            except AuthenticationError:
                st.error("❌ مفتاح API غير صحيح أو منتهي.")
            except RateLimitError:
                st.error("❌ تجاوزت الحد المسموح أو انتهى رصيد حسابك في OpenAI.")
            except APIConnectionError:
                st.error("❌ تعذر الاتصال بالخدمة. تحقق من الإنترنت وأعد المحاولة.")
            except APIStatusError as e:
                st.error(f"❌ رفضت الخدمة الطلب (رمز {e.status_code}).")
            except Exception as e:
                st.error("❌ حدث خطأ غير متوقع.")
                with st.expander("تفاصيل الخطأ"):
                    st.code(str(e))

# =========================================================
# 7. عرض النتائج
# =========================================================
def audio_buttons(english: str, semi: str, full: str) -> str:
    """أزرار نطق عبر المتصفح. النصوص تُخزَّن في data-* بعد escape، فلا تنكسر مع أي رمز."""
    spec = [
        ("English", english, "en-US", "#059669"),
        ("النصفي", semi, "ar-SA", "#6B7280"),
        ("الكامل", full, "ar-SA", "#1E3A8A"),
    ]
    buttons = ""
    for label, text, lang, color in spec:
        if text:
            buttons += (
                f'<button class="b" style="background:{color}" '
                f'data-t="{html.escape(text, quote=True)}" data-l="{lang}">🔊 {label}</button>'
            )
    return f"""
    <style>
      body {{ margin:0; direction:rtl; font-family:sans-serif; }}
      .b {{ color:#fff; border:none; border-radius:6px; padding:7px 12px;
            cursor:pointer; margin-left:6px; font-size:14px; }}
    </style>
    <div>{buttons}</div>
    <script>
      document.querySelectorAll('.b').forEach(function (b) {{
        b.addEventListener('click', function () {{
          if (!('speechSynthesis' in window)) return;
          window.speechSynthesis.cancel();
          var u = new SpeechSynthesisUtterance(b.dataset.t);
          u.lang = b.dataset.l;
          u.rate = 0.9;
          window.speechSynthesis.speak(u);
        }});
      }});
    </script>
    """


results = st.session_state.results
if results:
    st.markdown("---")
    for t in results:
        if not t["ok"]:
            st.markdown(
                f'<div class="note-card">⚠️ «{html.escape(t["input"])}»: '
                f'{html.escape(t["reason"] or "لم أتعرف على هذا المصطلح.")}</div>',
                unsafe_allow_html=True,
            )
            continue

        st.markdown(
            f"""
            <div class="term-card">
              <span class="lbl">الإنجليزية:</span> <span class="en">{html.escape(t["english"])}</span><br>
              <span class="lbl">التعريب النصفي:</span> {html.escape(t["semi_arabic"])}<br>
              <span class="lbl">التعريب الكامل:</span> <span class="full">{html.escape(t["full_arabic"])}</span><br>
              <span class="lbl">السبب:</span> {html.escape(t["reason"])}
            </div>
            """,
            unsafe_allow_html=True,
        )
        components.html(audio_buttons(t["english"], t["semi_arabic"], t["full_arabic"]), height=48)

    rows = [
        f'{t["english"]} | {t["semi_arabic"]} | {t["full_arabic"]} | {t["reason"]}'
        for t in results
        if t["ok"]
    ]
    if rows:
        st.download_button(
            "⬇️ تنزيل القائمة",
            data="الإنجليزية | التعريب النصفي | التعريب الكامل | السبب\n" + "\n".join(rows),
            file_name="المصطلحات.txt",
            mime="text/plain",
        )

    if st.button("🗑️ مسح النتائج"):
        st.session_state.results = None
        st.rerun()

# =========================================================
# 8. التذييل
# =========================================================
st.markdown("---")
st.markdown('<div class="footer">مُعرِّب المصطلحات العلمية © 2026</div>', unsafe_allow_html=True)
