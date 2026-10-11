"""Allowlisted operational errors; no document contents or secrets enter logs."""
MESSAGES = {
    'processor_configuration': 'Сервис распознавания не настроен. Документ сохранён; обратитесь к оператору платформы.',
    'processor_unavailable': 'Сервис распознавания временно недоступен. Документ сохранён, обработка будет повторена.',
    'processor_busy': 'Сервис распознавания занят. Документ сохранён и ожидает повторной обработки.',
    'processing_timeout': 'Распознавание заняло слишком много времени. Документ сохранён; попробуйте повторить обработку.',
    'invalid_document': 'Не удалось прочитать документ. Проверьте формат, защиту паролем и ограничение в 40 страниц.',
    'processor_error': 'Внутренняя ошибка обработки. Документ сохранён; можно повторить обработку или обратиться к оператору.',
}


class ProcessingFailure(Exception):
    def __init__(self, code):
        self.code = code if code in MESSAGES else 'processor_error'
        super().__init__(self.code)
