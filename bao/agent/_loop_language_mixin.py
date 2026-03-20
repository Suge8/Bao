from __future__ import annotations

from bao.agent import plan as plan_state
from bao.session.manager import Session

from ._loop_constants import CJK_CHAR_RE as _CJK_CHAR_RE
from ._loop_constants import LATIN_CHAR_RE as _LATIN_CHAR_RE
from ._loop_constants import SESSION_LANG_KEY as _SESSION_LANG_KEY


class LoopLanguageMixin:
    def _resolve_user_language(self) -> str:
        cfg_lang = getattr(getattr(self._config, "ui", None), "language", None)
        if isinstance(cfg_lang, str):
            normalized = cfg_lang.strip().lower()
            if normalized and normalized != "auto":
                return plan_state.normalize_language(normalized)
        try:
            from bao.config.onboarding import infer_language

            return plan_state.normalize_language(infer_language(self.prompt_root))
        except Exception:
            return "en"

    @staticmethod
    def _detect_message_language(text: str | None) -> str | None:
        if not isinstance(text, str):
            return None
        value = text.strip()
        if not value:
            return None
        cjk_count = len(_CJK_CHAR_RE.findall(value))
        latin_count = len(_LATIN_CHAR_RE.findall(value))
        if cjk_count > 0 and cjk_count >= latin_count:
            return "zh"
        if latin_count >= 3 and cjk_count == 0:
            return "en"
        return None

    def _resolve_session_language(
        self,
        session: Session,
        text: str | None = None,
    ) -> tuple[str, bool]:
        stored_raw = session.metadata.get(_SESSION_LANG_KEY)
        stored_lang = (
            plan_state.normalize_language(stored_raw)
            if isinstance(stored_raw, str) and stored_raw.strip()
            else ""
        )
        detected_lang = self._detect_message_language(text)
        if detected_lang:
            changed = stored_lang != detected_lang
            if changed:
                session.metadata[_SESSION_LANG_KEY] = detected_lang
            return detected_lang, changed
        if stored_lang:
            return stored_lang, False
        return self._resolve_user_language(), False
