"""User-facing text in every supported language.

Only the screens and bot messages the student sees are translated. The coaching conversation
itself happens in the student's own Claude, which already answers in the student's language.

Add a language by adding a column to MESSAGES: every key must exist in every language
(tests/test_i18n.py checks this).
"""
from __future__ import annotations

DEFAULT = "en"
LANGUAGES = {"en": "English", "tr": "Türkçe"}

MESSAGES: dict[str, dict[str, str]] = {
    # --- shared ----------------------------------------------------------
    "app_name": {"en": "Study Coach", "tr": "Çalışma Koçu"},
    "email": {"en": "Email", "tr": "E-posta"},
    "password": {"en": "Password", "tr": "Şifre"},
    "account_password": {"en": "Account password", "tr": "Hesap şifresi"},
    "too_many_attempts": {"en": "Too many attempts. Try again in 15 minutes.",
                          "tr": "Çok fazla deneme. 15 dakika sonra tekrar dene."},
    "wrong_credentials": {"en": "Wrong email or password.", "tr": "E-posta ya da şifre hatalı."},
    "wait_title": {"en": "Please wait", "tr": "Bekle"},
    "error_title": {"en": "Error", "tr": "Hata"},
    # --- login / sign-up (OAuth) -----------------------------------------
    "login_tab": {"en": "Sign in", "tr": "Giriş"},
    "signup_tab": {"en": "New account", "tr": "Yeni hesap"},
    "login_intro_signup": {"en": "Create an account to give your coach access to your notes. "
                                 "These details are stored only on this server.",
                           "tr": "Koçun notlarına erişebilmesi için hesap aç. Bu bilgiler yalnız bu sunucuda tutulur."},
    "login_intro_login": {"en": "Sign in to give your coach access to your notes. "
                                "These details are stored only on this server.",
                          "tr": "Koçun notlarına erişebilmesi için giriş yap. Bu bilgiler yalnız bu sunucuda tutulur."},
    "connecting_app": {"en": "Asking for access:", "tr": "Bağlanmak isteyen:"},
    "invite_code": {"en": "Invite code", "tr": "Davet kodu"},
    "signup_button": {"en": "Create account and connect", "tr": "Hesap aç ve bağlan"},
    "login_button": {"en": "Sign in and connect", "tr": "Giriş yap ve bağlan"},
    "app_fallback": {"en": "App", "tr": "Uygulama"},
    "err_password_short": {"en": "The password must be at least 8 characters.",
                           "tr": "Şifre en az 8 karakter olmalı."},
    "err_email": {"en": "Enter a valid email address.", "tr": "Geçerli bir e-posta yaz."},
    "err_invite": {"en": "That invite code is not valid.", "tr": "Davet kodu geçersiz."},
    "err_email_taken": {"en": "An account with this email already exists. Use the Sign in tab.",
                        "tr": "Bu e-postayla hesap var, Giriş sekmesini kullan."},
    "expired_title": {"en": "Link expired", "tr": "Süre doldu"},
    "request_not_found": {"en": "Connection request not found", "tr": "Bağlantı isteği bulunamadı"},
    "request_expired": {"en": "This connection request has expired", "tr": "Bağlantı isteğinin süresi doldu"},
    "reconnect_hint": {"en": "Go back to Claude or ChatGPT and connect the connector again.",
                       "tr": "Claude ya da ChatGPT'ye dönüp bağlayıcıyı yeniden bağla."},
    "connect_failed": {"en": "Could not connect", "tr": "Bağlanamadı"},
    "login_expired": {"en": "The sign-in request expired. Connect the connector again.",
                      "tr": "Giriş isteğinin süresi doldu, bağlayıcıyı yeniden bağla."},
    # --- Obsidian sync -----------------------------------------------------
    "obsidian_title": {"en": "Obsidian sync", "tr": "Obsidian eşitleme"},
    "obsidian_intro": {"en": "Get the WebDAV details for the <b>Remotely Save</b> plugin in Obsidian. "
                             "A new password is created each time and the old one stops working.",
                       "tr": "Obsidian'daki <b>Remotely Save</b> eklentisi için WebDAV bilgilerini al. "
                             "Her seferinde yeni şifre üretilir, eskisi geçersiz olur."},
    "obsidian_button": {"en": "Show details", "tr": "Bilgileri göster"},
    "obsidian_settings": {"en": "Remotely Save settings", "tr": "Remotely Save ayarları"},
    "obsidian_settings_intro": {"en": "In Remotely Save, set Remote Service to <b>Webdav</b> and enter the "
                                      "values below. This password is shown only once.",
                                "tr": "Remotely Save → Remote Service: <b>Webdav</b> seç ve aşağıdakileri gir. "
                                      "Bu şifre bir daha gösterilmez."},
    # --- upload page -------------------------------------------------------
    "upload_title": {"en": "Upload", "tr": "Yükle"},
    "upload_login_intro": {"en": "Sign in once with your coach account. This phone will be remembered.",
                           "tr": "Koç hesabınla bir kez giriş yap, bu telefon hatırlanır."},
    "upload_login_button": {"en": "Sign in", "tr": "Giriş yap"},
    "upload_intro": {"en": "A photo of a question you couldn't solve, or your study notes (PDF, Word, text). "
                           "Then tell your coach \"let's look at what I uploaded\".",
                     "tr": "Çözemediğin sorunun fotoğrafı ya da ders notun (PDF, Word, metin). "
                           "Sonra koça \"yüklediğime bakalım\" yaz."},
    "upload_note": {"en": "Note (optional)", "tr": "Not (isteğe bağlı)"},
    "upload_note_placeholder": {"en": "e.g. Endocrinology lecture notes, week 3",
                                "tr": "örn. Endokrin ders notu, 3. hafta"},
    "upload_button": {"en": "Upload", "tr": "Yükle"},
    "upload_telegram": {"en": "You can also get reminders and upload from Telegram:",
                        "tr": "Hatırlatmaları ve yüklemeyi Telegram'dan da yapabilirsin:"},
    "connect_telegram": {"en": "Connect Telegram", "tr": "Telegram'a bağla"},
    "upload_too_big": {"en": "The file is larger than 100 MB.", "tr": "Dosya 100 MB'tan büyük."},
    "upload_no_file": {"en": "No file selected.", "tr": "Dosya seçilmedi."},
    "upload_failed": {"en": "Upload failed. Please try again.", "tr": "Yükleme başarısız, tekrar dene."},
    "uploaded_title": {"en": "Uploaded", "tr": "Yüklendi"},
    "uploaded_hint": {"en": "Tell your coach \"let's look at what I uploaded\".",
                      "tr": "Koça \"yüklediğime bakalım\" yaz."},
    "upload_another": {"en": "Upload another", "tr": "Bir tane daha yükle"},
    "bot_not_ready": {"en": "The bot is not ready yet.", "tr": "Bot hazır değil."},
    # --- home --------------------------------------------------------------
    "home_intro": {"en": "Add it to Claude or ChatGPT as a custom connector:",
                   "tr": "Claude ya da ChatGPT'ye özel bağlayıcı olarak ekle:"},
    "home_upload": {"en": "Upload a question or notes", "tr": "Soru ya da ders notu yükle"},
    # --- Telegram bot ------------------------------------------------------
    "tg_help": {"en": "I'm your study coach's reminder bot.\n\n"
                      "• Send a photo of a question, a PDF or your notes: I save it to your vault and your coach "
                      "sees it in Claude.\n"
                      "• In the morning I send today's reviews and tasks; in the evening I ask whether you finished "
                      "your tasks.\n\n"
                      "Commands:\n"
                      "/today - send today's list now\n"
                      "/time 08:30 21:30 - change the morning and evening time\n"
                      "/timezone Europe/Berlin - change your time zone\n"
                      "/language en|tr - change the language\n"
                      "/mute - pause reminders, /unmute - turn them back on\n"
                      "/unlink - disconnect this chat",
                "tr": "Ben çalışma koçunun hatırlatma botuyum.\n\n"
                      "• Soru fotoğrafı, PDF ya da ders notu gönder: kasana kaydederim, Claude'da koçun görür.\n"
                      "• Sabah günün tekrarlarını ve görevlerini, akşam görevlerin bitip bitmediğini sorarım.\n\n"
                      "Komutlar:\n"
                      "/today - bugünün listesini şimdi gönder\n"
                      "/time 08:30 21:30 - sabah ve akşam saatini değiştir\n"
                      "/timezone Europe/Istanbul - saat dilimini değiştir\n"
                      "/language en|tr - dili değiştir\n"
                      "/mute - hatırlatmaları durdur, /unmute - yeniden başlat\n"
                      "/unlink - bu sohbetin bağlantısını kaldır"},
    "tg_not_linked": {"en": "This chat isn't linked to an account. Press \"Connect Telegram\" on the upload page.",
                      "tr": "Bu sohbet bir hesaba bağlı değil. Yükleme sayfasındaki \"Telegram'a bağla\" "
                            "düğmesine bas."},
    "tg_not_linked_short": {"en": "This chat isn't linked to an account.",
                            "tr": "Bu sohbet bir hesaba bağlı değil."},
    "tg_nothing_today": {"en": "Nothing due today. 🎉", "tr": "Bugün için tarihi gelen görev ya da tekrar yok. 🎉"},
    "tg_time_example": {"en": "Example: /time 08:30 21:30", "tr": "Örnek: /time 08:30 21:30"},
    "tg_time_set": {"en": "Done: morning {morning}, evening {evening}.",
                    "tr": "Tamam: sabah {morning}, akşam {evening}."},
    "tg_timezone_example": {"en": "Example: /timezone Europe/Berlin", "tr": "Örnek: /timezone Europe/Istanbul"},
    "tg_timezone_set": {"en": "Time zone set to {tz}.", "tr": "Saat dilimi {tz} oldu."},
    "tg_language_example": {"en": "Example: /language en", "tr": "Örnek: /language tr"},
    "tg_language_set": {"en": "I'll write in English from now on.", "tr": "Bundan sonra Türkçe yazacağım."},
    "tg_muted": {"en": "Reminders paused. Send /unmute to turn them back on.",
                 "tr": "Hatırlatmaları durdurdum. /unmute ile açarsın."},
    "tg_unmuted": {"en": "Reminders are on again.", "tr": "Hatırlatmalar yeniden açık."},
    "tg_unlinked": {"en": "Disconnected. Nothing in your vault was deleted.",
                    "tr": "Bağlantı kaldırıldı. Kasandaki hiçbir şey silinmedi."},
    "tg_chat_elsewhere": {"en": "Chatting and solving questions happens in Claude: write to your coach there. "
                                "You can send photos or PDFs here.",
                          "tr": "Sohbet ve soru çözümü Claude'da: koçuna orada yaz. Buraya fotoğraf ya da PDF "
                                "gönderebilirsin."},
    "tg_bad_code": {"en": "This link code is invalid or expired. Press \"Connect Telegram\" on the upload page again.",
                    "tr": "Bağlantı kodu geçersiz ya da süresi dolmuş. Yükleme sayfasından \"Telegram'a bağla\" "
                          "düğmesine yeniden bas."},
    "tg_linked": {"en": "Connected! ✅ I'll write at {morning} in the morning and {evening} in the evening ({tz}).",
                  "tr": "Bağlandı! ✅ Sabah {morning} ve akşam {evening} yazacağım ({tz})."},
    "tg_file_too_big": {"en": "Telegram bots can't receive files larger than 20 MB. Send this one from the upload "
                              "page: {url}",
                        "tr": "Telegram botları 20 MB'tan büyük dosyayı alamıyor. Bunu yükleme sayfasından gönder: "
                              "{url}"},
    "tg_saved": {"en": "Saved: {paths}\n\nTell your coach in Claude \"let's look at what I uploaded\".",
                 "tr": "Kaydettim: {paths}\n\nClaude'da koçuna \"yüklediğime bakalım\" yaz."},
    # --- reminders ---------------------------------------------------------
    "rem_morning": {"en": "Good morning! Here's what's waiting for you today:",
                    "tr": "Günaydın! Bugün seni bekleyenler:"},
    "rem_tasks": {"en": "📋 Tasks ({n})", "tr": "📋 Görevler ({n})"},
    "rem_overdue": {"en": " (overdue)", "tr": " (gecikti)"},
    "rem_reviews": {"en": "🔁 Due for review ({n})", "tr": "🔁 Tekrar zamanı gelenler ({n})"},
    "rem_start": {"en": "To start, tell your coach in Claude \"let's begin\".",
                  "tr": "Başlamak için Claude'da koçuna \"başlayalım\" yaz."},
    "rem_task_question": {"en": "Today's task: {title}\nDid you finish it?", "tr": "Bugünkü görev: {title}\nBitti mi?"},
    "rem_done_button": {"en": "✅ Done", "tr": "✅ Bitti"},
    "rem_tomorrow_button": {"en": "➡️ Move to tomorrow", "tr": "➡️ Yarına kaldı"},
    "rem_button_invalid": {"en": "This button is no longer valid.", "tr": "Bu düğme artık geçerli değil."},
    "rem_task_missing": {"en": "I couldn't find this task.", "tr": "Bu görev bulunamadı."},
    "rem_task_closed": {"en": "This task is already closed.", "tr": "Bu görev zaten kapanmış."},
    "rem_marked_done": {"en": "Great, marked as done. 👏", "tr": "Harika, bitti olarak işaretledim. 👏"},
    "rem_moved": {"en": "OK, moved to tomorrow.", "tr": "Tamam, yarına aldım."},
    "rem_save_failed": {"en": "I couldn't save that; tell your coach and they'll update it.",
                        "tr": "Kaydedemedim; koçuna söylersen o güncellesin."},
    "rem_task_changed": {"en": "The task changed in the meantime; tell your coach and they'll update it.",
                         "tr": "Görev bu arada değişmiş; koçuna söylersen o güncellesin."},
}


def t(lang: str | None, key: str, **values: object) -> str:
    """The text for `key` in `lang`, falling back to the default language."""
    entry = MESSAGES[key]
    text = entry.get(lang or DEFAULT) or entry[DEFAULT]
    return text.format(**values) if values else text


def normalize(lang: str | None) -> str | None:
    """'tr-TR' -> 'tr'; None if the language isn't supported."""
    if not lang:
        return None
    code = lang.strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGUAGES else None


def from_accept_language(header: str | None) -> str:
    """Picks the best supported language from an Accept-Language header."""
    choices = []
    for i, part in enumerate((header or "").split(",")):
        code, _, params = part.strip().partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        if normalize(code):
            choices.append((-q, i, normalize(code)))
    return min(choices)[2] if choices else DEFAULT
