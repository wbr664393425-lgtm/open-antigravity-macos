"""Глобальное состояние сессии запуска.

Модуль намеренно без зависимостей, чтобы его могли импортировать
и cli.py, и console.py, и captcha.py без циклов.

ASSUME_YES — неинтерактивный режим (`agpatch patch -y`): все
подтверждения считаются согласием, паузы и очистка экрана
отключаются, ввод не запрашивается.
"""

ASSUME_YES = False
CLEAR_SCREEN = True


def set_assume_yes(enabled=True):
    global ASSUME_YES
    ASSUME_YES = bool(enabled)


def is_assume_yes():
    return ASSUME_YES


def set_clear_screen(enabled=True):
    global CLEAR_SCREEN
    CLEAR_SCREEN = bool(enabled)


def is_clear_screen():
    return CLEAR_SCREEN
