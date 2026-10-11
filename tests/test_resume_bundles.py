"""Identity separation for resume collections, independent of model availability."""
from pathlib import Path

from worker import extraction


def page(number, text):
    return {'page': number, 'text': text, 'method': 'pdf_text', 'confidence': 1.0}


def test_distinct_people_never_share_extracted_contacts(monkeypatch):
    pages = [
        page(1, 'ОБРАЗЕЦ:\nИВАНОВА МАРИЯ СЕРГЕЕВНА\nfirst@example.test\nНавыки: Python'),
        page(2, 'ОБРАЗЕЦ\nИВАНОВ ИВАН СЕРГЕЕВИЧ\nsecond@example.test\nНавыки: Java'),
        page(3, 'ОБРАЗЕЦ ИВАНОВА МАРИЯ СЕРГЕЕВНА\nthird@example.test\nНавыки: SQL'),
    ]
    monkeypatch.setattr(extraction, 'read_pages', lambda *args: pages)
    def unavailable(*args, **kwargs):
        raise ConnectionError('Offline model')
    monkeypatch.setattr(extraction, 'llm_extract', unavailable)
    result = extraction.extract(Path('unused.pdf'), 'resume')
    assert result['fields'] == {}
    assert len(result['profiles']) == 3
    for index, email in enumerate(['first@example.test', 'second@example.test', 'third@example.test']):
        profile = result['profiles'][index]
        assert profile['fields']['email'] == email
        assert profile['provenance']['email']['page'] == index + 1
        assert len(profile['pages']) == 1
        assert profile['fields']['full_name']
        for other in [p for p in result['profiles'] if p is not profile]:
            assert email not in other['fields']['description']


def test_repeated_name_on_continuation_page_stays_one_resume():
    pages = [page(1, 'Иванов Иван Сергеевич\nОпыт работы'), page(2, 'Иванов Иван Сергеевич\nПродолжение опыта')]
    assert len(extraction.split_resumes(pages)) == 1


def test_new_person_without_sample_marker_starts_new_resume():
    pages = [page(1, 'Иванов Иван Сергеевич\nОпыт работы'), page(2, 'Петров Пётр Петрович\nОпыт работы')]
    assert len(extraction.split_resumes(pages)) == 2


def test_bare_continuation_page_stays_in_current_resume():
    pages = [page(1, 'Иванов Иван Сергеевич\nОпыт работы'), page(2, 'Образование\nПроекты и публикации')]
    assert len(extraction.split_resumes(pages)) == 1
