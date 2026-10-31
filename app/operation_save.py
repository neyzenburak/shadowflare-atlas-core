"""Explicit opt-in pre-operation character save and backup."""

def save_choice(value=False):
    if not isinstance(value,bool):raise ValueError('İşlem öncesi kayıt seçimi aç/kapat olmalı.')
    return value


def optional_save(enabled=False,timeout=30):
    if not save_choice(enabled):return None
    from native_save import save_current
    return save_current(timeout)
