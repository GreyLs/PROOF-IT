from worker.employment import compatible_dates,date_bounds,same_company,role_family,explicit_teamlead_alias

def test_date_precision_and_real_deviations():
    assert compatible_dates('февраль 2022','01.02.2022') is True
    assert compatible_dates('2022-02','28.02.2022') is True
    assert compatible_dates('Feb 2022','28.02.2022 г.') is True
    assert compatible_dates('февр. 2022','2022-02-01') is True
    assert compatible_dates('2022','02.06.2022') is True
    assert compatible_dates('январь 2022','01.04.2022') is False
    assert compatible_dates('2023','2022') is False
    assert compatible_dates('по настоящее время','') is None
    assert date_bounds('31.02.2022') is None

def test_company_and_role_aliases():
    assert same_company('ООО «ВекторСофт»','ВекторСофт')
    assert not same_company('ВекторСофт','ДругойРаботодатель')
    assert role_family('Тимлид разработки')==role_family('Руководитель группы разработки')=='teamlead'
    assert role_family('CTO')==role_family('Технический директор')=='cto'
    assert role_family('Разработчик')!=role_family('CTO')
    assert explicit_teamlead_alias('тимлид','руководитель группы')
    assert explicit_teamlead_alias('тимлид разработки','руководитель группы разработки')
    assert not explicit_teamlead_alias('тимлид QA','руководитель группы разработки')
